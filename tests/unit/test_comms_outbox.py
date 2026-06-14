"""Store-and-forward outbox: triage order, eviction, expiry, and flush (BL-077)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from nous.state.comms_outbox import CommsOutbox, OutboxPackage, Precedence
from nous.subsystems.comms import CommsSubsystem


def _comms(*, links: list[Mapping[str, Any]] | None = None) -> CommsSubsystem:
    default: list[Mapping[str, Any]] = links or [
        {
            "id": "lte",
            "bandwidth_bps": 20_000_000,
            "rssi_dbm_nominal": -75,
            "loss_pct_nominal": 0.5,
            "max_age_s": 30.0,
        },
        {
            "id": "lora",
            "bandwidth_bps": 50_000,
            "rssi_dbm_nominal": -110,
            "loss_pct_nominal": 2.0,
            "max_age_s": 120.0,
        },
    ]
    return CommsSubsystem({"comms": {"links": default}})


def _outbox(**outbox_cfg: Any) -> CommsOutbox:
    profile: dict[str, Any] = {"comms": {"links": []}}
    if outbox_cfg:
        profile["comms"]["outbox"] = outbox_cfg
    return CommsOutbox(profile)


# -- precedence ----------------------------------------------------------


def test_precedence_rank_order() -> None:
    assert Precedence.ROUTINE.rank() < Precedence.PRIORITY.rank()
    assert Precedence.PRIORITY.rank() < Precedence.IMMEDIATE.rank()
    assert Precedence.IMMEDIATE.rank() < Precedence.FLASH.rank()


def test_precedence_parse_is_lenient() -> None:
    assert Precedence.parse("flash") is Precedence.FLASH
    assert Precedence.parse("FLASH") is Precedence.FLASH
    assert Precedence.parse("garbage") is Precedence.ROUTINE
    assert Precedence.parse("") is Precedence.ROUTINE
    assert Precedence.parse(None) is Precedence.ROUTINE
    assert Precedence.parse(Precedence.IMMEDIATE) is Precedence.IMMEDIATE


# -- enqueue admission ---------------------------------------------------


def test_enqueue_accepts_and_counts() -> None:
    ob = _outbox()
    result = ob.enqueue("lte", 1000, now_s=0.0)
    assert result.accepted is True
    assert ob.depth() == 1
    assert ob.queued_bytes() == 1000
    assert ob.enqueued_total == 1


def test_enqueue_rejects_nonpositive_size() -> None:
    ob = _outbox()
    assert ob.enqueue("lte", 0, now_s=0.0).accepted is False
    assert ob.enqueue("lte", -5, now_s=0.0).accepted is False
    assert ob.depth() == 0


def test_enqueue_rejects_oversize_package() -> None:
    ob = _outbox(max_bytes=500)
    result = ob.enqueue("lte", 600, now_s=0.0)
    assert result.accepted is False
    assert "exceeds outbox max_bytes" in result.reason
    assert ob.rejected_total == 1


def test_disabled_outbox_refuses_enqueue() -> None:
    ob = _outbox(enabled=False)
    result = ob.enqueue("lte", 100, now_s=0.0)
    assert result.accepted is False
    assert result.reason == "outbox disabled"
    assert ob.depth() == 0


# -- triage order --------------------------------------------------------


def test_head_and_order_follow_precedence_then_age() -> None:
    ob = _outbox()
    r_routine = ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.ROUTINE)
    ob.enqueue("lte", 100, now_s=1.0, precedence=Precedence.FLASH)
    ob.enqueue("lte", 100, now_s=2.0, precedence=Precedence.PRIORITY)
    # Two routine packages at different ages to check the FIFO tie-break.
    ob.enqueue("lte", 100, now_s=3.0, precedence=Precedence.ROUTINE)

    order = [pkg.precedence for pkg in ob.packages()]
    assert order == [
        Precedence.FLASH,
        Precedence.PRIORITY,
        Precedence.ROUTINE,
        Precedence.ROUTINE,
    ]
    head = ob.head()
    assert head is not None and head.precedence is Precedence.FLASH
    # The older routine sorts ahead of the newer one.
    routines = [pkg for pkg in ob.packages() if pkg.precedence is Precedence.ROUTINE]
    assert routines[0].package_id == r_routine.package.package_id  # type: ignore[union-attr]


# -- eviction (the triage) ----------------------------------------------


def test_higher_precedence_evicts_lowest_oldest() -> None:
    ob = _outbox(max_packages=2)
    first = ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.ROUTINE)
    ob.enqueue("lte", 100, now_s=1.0, precedence=Precedence.ROUTINE)
    result = ob.enqueue("lte", 100, now_s=2.0, precedence=Precedence.FLASH)

    assert result.accepted is True
    assert first.package is not None
    assert first.package.package_id in result.evicted
    assert ob.dropped_overflow_total == 1
    assert ob.depth() == 2
    precs = sorted(pkg.precedence for pkg in ob.packages())
    assert Precedence.FLASH in precs


def test_full_queue_refuses_equal_precedence() -> None:
    ob = _outbox(max_packages=1)
    ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.ROUTINE)
    result = ob.enqueue("lte", 100, now_s=1.0, precedence=Precedence.ROUTINE)
    assert result.accepted is False
    assert "no lower-precedence package to evict" in result.reason
    assert ob.rejected_total == 1
    assert ob.depth() == 1


def test_eviction_by_byte_budget() -> None:
    ob = _outbox(max_bytes=1000, max_packages=100)
    ob.enqueue("lte", 800, now_s=0.0, precedence=Precedence.ROUTINE)
    # 800 + 800 > 1000, so the higher-precedence arrival evicts the routine.
    result = ob.enqueue("lte", 800, now_s=1.0, precedence=Precedence.IMMEDIATE)
    assert result.accepted is True
    assert ob.dropped_overflow_total == 1
    assert ob.depth() == 1
    assert ob.queued_bytes() == 800


def test_lower_precedence_arrival_refused_when_full_of_higher() -> None:
    ob = _outbox(max_packages=1)
    ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.FLASH)
    result = ob.enqueue("lte", 100, now_s=1.0, precedence=Precedence.ROUTINE)
    assert result.accepted is False
    assert ob.depth() == 1
    head = ob.head()
    assert head is not None and head.precedence is Precedence.FLASH


# -- expiry --------------------------------------------------------------


def test_expiry_purged_on_next_enqueue() -> None:
    ob = _outbox()
    ob.enqueue("lte", 100, now_s=0.0, ttl_s=10.0)
    # Past TTL: the next enqueue purges the stale package first.
    ob.enqueue("lte", 100, now_s=20.0, ttl_s=10.0)
    assert ob.expired_total == 1
    assert ob.depth() == 1


def test_default_ttl_from_profile_applies() -> None:
    ob = _outbox(default_ttl_s=5.0)
    res = ob.enqueue("lte", 100, now_s=0.0)
    assert res.package is not None
    assert res.package.expiry_ts_s == 5.0


def test_ttl_zero_means_no_expiry() -> None:
    ob = _outbox(default_ttl_s=5.0)
    res = ob.enqueue("lte", 100, now_s=0.0, ttl_s=0.0)
    assert res.package is not None
    assert res.package.expiry_ts_s is None


# -- flush ---------------------------------------------------------------


def test_flush_delivers_in_triage_order_on_live_link() -> None:
    comms = _comms()
    ob = _outbox()
    routine = ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.ROUTINE)
    flash = ob.enqueue("lte", 100, now_s=1.0, precedence=Precedence.FLASH)
    priority = ob.enqueue("lte", 100, now_s=2.0, precedence=Precedence.PRIORITY)

    result = ob.flush(comms, now_s=3.0)
    assert result.delivered == [
        flash.package.package_id,  # type: ignore[union-attr]
        priority.package.package_id,  # type: ignore[union-attr]
        routine.package.package_id,  # type: ignore[union-attr]
    ]
    assert result.delivered_bytes == 300
    assert ob.depth() == 0
    assert ob.delivered_total == 3


def test_flush_defers_when_link_down() -> None:
    comms = _comms()
    comms.set_link_state("lte", connected=False)
    ob = _outbox()
    pkg = ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.FLASH)
    result = ob.flush(comms, now_s=1.0)
    assert result.delivered == []
    assert pkg.package is not None
    assert pkg.package.package_id in result.deferred
    assert ob.depth() == 1
    # The deferred package records the failed attempt.
    assert ob.packages()[0].attempts == 1


def test_store_and_forward_survives_outage_then_recovers() -> None:
    comms = _comms()
    comms.set_link_state("lte", connected=False)
    ob = _outbox()
    ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.IMMEDIATE)

    deferred = ob.flush(comms, now_s=1.0)
    assert deferred.delivered == []
    assert ob.depth() == 1

    comms.clear_link_override("lte")  # link recovers
    recovered = ob.flush(comms, now_s=2.0)
    assert len(recovered.delivered) == 1
    assert ob.depth() == 0


def test_flush_independent_links() -> None:
    comms = _comms()
    comms.set_link_state("lora", connected=False)
    ob = _outbox()
    ob.enqueue("lte", 100, now_s=0.0)
    ob.enqueue("lora", 100, now_s=0.0)
    result = ob.flush(comms, now_s=1.0)
    assert len(result.delivered) == 1
    assert len(result.deferred) == 1
    assert ob.depth() == 1  # the lora package stays queued


def test_flush_unknown_link_defers() -> None:
    comms = _comms()
    ob = _outbox()
    ob.enqueue("ghost", 100, now_s=0.0)
    result = ob.flush(comms, now_s=1.0)
    assert result.delivered == []
    assert ob.depth() == 1


def test_flush_drops_expired_without_delivering() -> None:
    comms = _comms()
    ob = _outbox()
    pkg = ob.enqueue("lte", 100, now_s=0.0, ttl_s=10.0)
    result = ob.flush(comms, now_s=20.0)
    assert pkg.package is not None
    assert pkg.package.package_id in result.expired
    assert result.delivered == []
    assert ob.expired_total == 1
    assert ob.depth() == 0


def test_flush_budget_rate_limits_per_link() -> None:
    comms = _comms()
    ob = _outbox()
    ob.enqueue("lte", 80, now_s=0.0, precedence=Precedence.FLASH)
    ob.enqueue("lte", 80, now_s=1.0, precedence=Precedence.PRIORITY)
    # Budget fits only the first (higher-precedence) package.
    result = ob.flush(comms, now_s=2.0, link_budget_bytes={"lte": 100.0})
    assert len(result.delivered) == 1
    assert result.delivered_bytes == 80
    assert ob.depth() == 1
    # The remaining package is still PRIORITY and still queued.
    head = ob.head()
    assert head is not None and head.precedence is Precedence.PRIORITY


def test_head_of_line_blocking_preserves_precedence() -> None:
    comms = _comms()
    ob = _outbox()
    # A big FLASH that will not fit the budget must block a small ROUTINE
    # behind it on the same link, never letting the routine jump ahead.
    ob.enqueue("lte", 200, now_s=0.0, precedence=Precedence.FLASH)
    ob.enqueue("lte", 10, now_s=1.0, precedence=Precedence.ROUTINE)
    result = ob.flush(comms, now_s=2.0, link_budget_bytes={"lte": 100.0})
    assert result.delivered == []
    assert ob.depth() == 2


def test_flush_tick_uses_link_bandwidth() -> None:
    comms = _comms()
    ob = _outbox()
    ob.enqueue("lora", 1000, now_s=0.0)
    # lora is 50_000 bps -> 6250 bytes per second; dt=0.5 -> 3125 bytes budget.
    result = ob.flush_tick(comms, dt=0.5, now_s=1.0)
    assert len(result.delivered) == 1
    assert ob.depth() == 0


def test_flush_tick_respects_narrow_budget() -> None:
    comms = _comms()
    ob = _outbox()
    # 4000 bytes will not fit lora's 3125-byte per-tick budget at dt=0.5.
    ob.enqueue("lora", 4000, now_s=0.0)
    result = ob.flush_tick(comms, dt=0.5, now_s=1.0)
    assert result.delivered == []
    assert ob.depth() == 1


# -- status surface ------------------------------------------------------


def test_status_reports_breakdown_and_counters() -> None:
    ob = _outbox()
    ob.enqueue("lte", 100, now_s=0.0, precedence=Precedence.FLASH, ttl_s=50.0)
    ob.enqueue("lora", 200, now_s=0.0, precedence=Precedence.ROUTINE)
    status = ob.status(now_s=1.0)
    assert status["depth"] == 2
    assert status["queued_bytes"] == 300
    assert status["by_precedence"]["flash"] == 1
    assert status["by_precedence"]["routine"] == 1
    assert status["by_link"] == {"lte": 1, "lora": 1}
    assert status["head"]["precedence"] == "flash"
    assert status["head"]["ttl_remaining_s"] == 49.0
    assert status["counters"]["enqueued"] == 2


def test_outbox_package_to_dict_is_json_safe() -> None:
    pkg = OutboxPackage(
        package_id=1,
        link_id="lte",
        size_bytes=100,
        precedence=Precedence.IMMEDIATE,
        kind="cot",
        enqueued_ts_s=1.23456,
        expiry_ts_s=11.23456,
    )
    body = pkg.to_dict()
    assert body["precedence"] == "immediate"
    assert body["enqueued_ts_s"] == 1.235
    assert body["expiry_ts_s"] == 11.235


# -- BL-048 / ADR 0053: probabilistic delivery over a lossy propagation link --


def _relay_link() -> Mapping[str, Any]:
    return {
        "id": "relay",
        "bandwidth_bps": 2_000_000,
        "rssi_dbm_nominal": -80,
        "loss_pct_nominal": 0.5,
        "max_age_s": 600.0,
        "propagation": {
            "peer": {"lat": 47.0, "lon": 12.98, "alt_m": 520},
            "tx_power_dbm": 20.0,
            "frequency_hz": 2.4e9,
            "excess_loss_db": 5.0,
            "noise_floor_dbm": -100.0,
            "snr_floor_db": 5.0,
            "snr_full_db": 20.0,
            "good_rssi_dbm": -85.0,
            "sensitivity_dbm": -115.0,
        },
    }


def _relay_comms_at(lon: float) -> CommsSubsystem:
    """A propagation-linked subsystem with the device at the given longitude.

    Nearer the relay (smaller lon delta from 12.98) is a healthier, higher-
    capacity link; further east is lossier with less capacity.
    """
    comms = CommsSubsystem(
        {"comms": {"links": [_relay_link()]}},
        position_fn=lambda: (47.0, lon, 500.0),
    )
    comms.step(1.0)  # solve the budget
    return comms


def test_lossy_propagation_link_defers_some_deliveries() -> None:
    import numpy as np

    comms = _relay_comms_at(13.30)
    relay = comms.link("relay")
    assert relay is not None and relay.loss_pct > 10.0

    profile: dict[str, Any] = {"comms": {"links": []}}
    ob = CommsOutbox(profile, rng=np.random.default_rng(0))
    for _ in range(20):
        ob.enqueue("relay", 100, now_s=0.0)
    result = ob.flush(comms, now_s=0.0)
    # The channel lost at least one transmission, so not everything shipped.
    assert len(result.deferred) >= 1


def test_without_rng_flush_is_all_or_nothing() -> None:
    comms = _relay_comms_at(13.30)
    profile: dict[str, Any] = {"comms": {"links": []}}
    ob = CommsOutbox(profile)  # no rng: probabilistic loss is off
    for _ in range(20):
        ob.enqueue("relay", 100, now_s=0.0)
    result = ob.flush(comms, now_s=0.0)
    assert len(result.delivered) == 20
    assert result.deferred == []


def test_flush_tick_budget_tracks_capacity_not_bandwidth() -> None:
    """ADR 0053 (Copilot review): the per-tick drain budget is the link's
    SNR-derived capacity, so a propagation link whose capacity has fallen below
    its rated bandwidth does not drain faster than it can sustain. A static link
    is unchanged because its capacity equals its bandwidth."""
    comms = _relay_comms_at(13.0)  # healthy (low loss) but capacity < bandwidth
    relay = comms.link("relay")
    assert relay is not None
    assert 0.0 < relay.capacity_bps < relay.bandwidth_bps
    assert relay.loss_pct < 5.0  # loss is not the limiter here, the budget is

    profile: dict[str, Any] = {"comms": {"links": []}}
    ob = CommsOutbox(profile)  # no rng: isolate the budget from probabilistic loss
    for _ in range(40):
        ob.enqueue("relay", 10_000, now_s=0.0)
    result = ob.flush_tick(comms, dt=1.0, now_s=0.0)

    cap_budget = relay.capacity_bps / 8.0
    bandwidth_budget = relay.bandwidth_bps / 8.0
    # Drains within the capacity budget (one package of slack), well under the
    # larger bandwidth budget the pre-fix code would have allowed.
    assert result.delivered_bytes <= cap_budget + 10_000
    assert result.delivered_bytes < bandwidth_budget
