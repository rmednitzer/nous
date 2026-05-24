"""Regression tests pinning closed audit findings.

This file is the runtime counterpart to ``AUDIT.md`` and
``docs/audit-2026-05-23.md``. Each class names one finding id and
asserts the specific behaviour that closed it. A future change that
re-opens the finding surfaces here, with the original defect summarised
in the class docstring rather than re-discovered from scratch.

The pattern is: one class per defect, prior bug documented in the
docstring, tests asserting the fix. Findings that are still open are
not represented; add a class only after the fix lands.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree

import pytest

from nous.anthropic_client import CallCap
from nous.estimators.biometrics import BiometricsKalman
from nous.estimators.compute import ComputeKalman
from nous.estimators.sensors import EnvironmentalKalman
from nous.estimators.storage import StorageKalman
from nous.estimators.thermal import ThermalKalman
from nous.interop.cot import CotAdapter
from nous.interop.misb_klv import MisbKlvAdapter
from nous.types import Observation


def _now() -> float:
    return datetime.now(UTC).timestamp()


class TestC1AnthropicCapFsyncsInsideLock:
    """C1: the daily-cap counter must fsync inside the flock.

    Original defect (``AUDIT.md`` C1, 2026-05-20): ``CallCap.increment``
    opened the counter file under an exclusive flock, mutated the JSON
    payload, then released the lock in a ``finally`` block before the
    file buffer reached stable storage. A second process holding the
    lock immediately after release could therefore read the pre-flush
    state and double-count the same day, breaching the daily-cap
    invariant documented in ADR-0005.

    Fix: ``fh.flush()`` + ``os.fsync(fh.fileno())`` are now executed
    while the flock is still held, and an ``OSError`` from fsync raises
    ``CapExhausted`` instead of returning a success that the caller
    cannot rely on.
    """

    def test_increment_persists_state_before_returning(self, tmp_path: Path) -> None:
        cap = CallCap(tmp_path / "count", cap=10)
        count, configured = cap.increment()

        raw = (tmp_path / "count").read_text(encoding="utf-8")
        state = json.loads(raw)

        assert count == 1
        assert configured == 10
        assert state["count"] == 1
        assert state["date"] == datetime.now(UTC).strftime("%Y-%m-%d")

    def test_second_process_reads_committed_state(self, tmp_path: Path) -> None:
        first = CallCap(tmp_path / "count", cap=10)
        first.increment()
        second = CallCap(tmp_path / "count", cap=10)
        count, _ = second.increment()
        assert count == 2


class TestC4MisbKlvRefusesOverflow:
    """C4: MISB KLV must refuse over-range keys and over-budget values.

    Original defect (``AUDIT.md`` C4, 2026-05-20): the TLV helper applied
    ``key & 0xff`` and ``len(value) & 0xff``, silently truncating any
    MISB ST 0601 tag above 255 and any value over 255 bytes. A
    downstream KLV parser would either reject the malformed frame or,
    worse, misinterpret it.

    Fix: ``MisbKlvAdapter.encode`` now validates the key range
    ``[1, 255]`` explicitly and raises ``ValueError`` when a value
    exceeds ``max_value_len``. The BER length encoder uses short form
    below 128 and long form above, never truncates.
    """

    def test_refuses_oversized_value(self) -> None:
        adapter = MisbKlvAdapter(max_value_len=64)
        with pytest.raises(ValueError, match="max"):
            adapter.encode({"ts_s": _now(), "5": "x" * 1000})

    def test_refuses_key_outside_valid_range(self) -> None:
        adapter = MisbKlvAdapter()
        with pytest.raises(ValueError, match=r"\[1, 255\]"):
            adapter.encode({"ts_s": _now(), "0": "value"})

    def test_long_form_length_round_trip(self) -> None:
        adapter = MisbKlvAdapter(max_value_len=4096)
        payload = adapter.encode({"ts_s": _now(), "5": "x" * 500})
        decoded = adapter.decode(payload)
        assert "error" not in decoded
        assert decoded["items"][5] == ("x" * 500).encode().hex()


class TestC5StubEstimatorsActuallyFilter:
    """C5: every advertised Kalman must update its covariance.

    Original defect (``AUDIT.md`` C5, 2026-05-20): ``ThermalKalman`` and
    ``ComputeKalman`` (and the storage / sensors / biometrics stubs that
    followed the same pattern) copied each observation into the state
    and returned a constant ``covariance`` dict that was chosen at
    construction and never updated. A controller reading
    ``self_estimator_status`` saw a plausible covariance and believed
    the filter was running. This is the most dangerous shape a stub can
    take: a working interface returning misleading values.

    Fix: each estimator now runs a real Kalman update whose posterior
    variance shrinks under a confident observation. The shrink is
    asserted here against the construction-time prior; the parallel
    property suite in ``test_estimator_properties.py`` extends the
    invariant under arbitrary input.
    """

    def test_thermal_update_shrinks_variance(self) -> None:
        k = ThermalKalman()
        v0 = k.state().covariance["junction_c"]
        k.update(
            Observation(
                source="thermal",
                ts_s=1.0,
                payload={"junction_c": 50.0},
                noise={"junction_c_sigma": 0.5},
            )
        )
        assert k.state().covariance["junction_c"] < v0

    def test_compute_update_shrinks_variance(self) -> None:
        k = ComputeKalman(initial_load_pct=20.0, initial_draw_w=40.0)
        v0 = k.state().covariance["load_pct"]
        k.update(
            Observation(
                source="compute",
                ts_s=1.0,
                payload={"load_pct": 50.0, "draw_w": 60.0},
                noise={"load_pct_sigma": 1.0, "draw_w_sigma": 2.0},
            )
        )
        assert k.state().covariance["load_pct"] < v0

    def test_storage_update_shrinks_variance(self) -> None:
        k = StorageKalman(initial_used_gib=100.0, initial_wear_pct=10.0)
        v0 = k.state().covariance["used_gib"]
        k.update(
            Observation(
                source="storage",
                ts_s=1.0,
                payload={"used_gib": 120.0, "wear_pct": 11.0},
                noise={"used_gib_sigma": 1.0, "wear_pct_sigma": 0.05},
            )
        )
        assert k.state().covariance["used_gib"] < v0

    def test_sensors_update_shrinks_variance(self) -> None:
        k = EnvironmentalKalman()
        v0 = k.state().covariance["temp_c"]
        k.update(
            Observation(
                source="sensors",
                ts_s=1.0,
                payload={"temp_c": 22.0, "humidity_pct": 55.0, "baro_kpa": 101.3},
                noise={
                    "temp_c_sigma": 0.2,
                    "humidity_pct_sigma": 1.0,
                    "baro_kpa_sigma": 0.05,
                },
            )
        )
        assert k.state().covariance["temp_c"] < v0

    def test_biometrics_update_shrinks_variance(self) -> None:
        k = BiometricsKalman()
        v0 = k.state().covariance["heart_rate_bpm"]
        k.update(
            Observation(
                source="biometrics",
                ts_s=1.0,
                payload={"heart_rate_bpm": 78.0, "core_temp_c": 37.1},
                noise={"heart_rate_bpm_sigma": 1.0, "core_temp_c_sigma": 0.05},
            )
        )
        assert k.state().covariance["heart_rate_bpm"] < v0


class TestH3CotEventCarriesRequiredAttributes:
    """H3: CoT events must carry ``time``, ``start``, ``stale``, and ``how``.

    Original defect (``AUDIT.md`` H3, 2026-05-20): the encoder emitted
    only ``version``, ``uid``, and ``type`` on the ``<event>`` root,
    plus a ``<point>`` with accuracy fields zeroed. CoT 2.0 requires
    the four temporal / provenance attributes. A TAK server consuming
    such a frame displays the unit but with no time-to-live (stale
    immediately) and no provenance.

    Fix: ``CotAdapter.encode`` now writes all four. ``stale`` is
    derived from ``stale_s`` past ``time`` so the frame is renderable.
    The XXE-safe decoder explicitly refuses ``DOCTYPE`` / ``ENTITY``.
    """

    def test_event_root_has_required_attributes(self) -> None:
        adapter = CotAdapter()
        payload = adapter.encode({"ts_s": _now(), "lat": 38.0, "lon": -77.0})
        root = ElementTree.fromstring(payload)
        assert root.tag == "event"
        for attr in ("time", "start", "stale", "how"):
            assert attr in root.attrib, f"missing required attribute: {attr}"

    def test_stale_is_after_start(self) -> None:
        adapter = CotAdapter(stale_s=120.0)
        payload = adapter.encode({"ts_s": _now(), "lat": 0.0, "lon": 0.0})
        root = ElementTree.fromstring(payload)
        assert root.attrib["stale"] > root.attrib["start"]

    def test_decoder_refuses_doctype(self) -> None:
        adapter = CotAdapter()
        malicious = b"<!DOCTYPE event SYSTEM 'http://evil'><event/>"
        decoded = adapter.decode(malicious)
        assert "error" in decoded


class TestM8EngineTickIsUnitTestable:
    """M8: ``engine.tick()`` must be reachable from a unit test.

    Original defect (``AUDIT.md`` M8, 2026-05-20): no test imported the
    engine, advanced it by one tick, and asserted on the resulting
    ``TickContext``. The tick loop was the spine of the simulator and
    yet its direct unit-level contract was unwitnessed. The integration
    suite exercised it transitively, but a unit-level guard against
    "tick is silently broken" was missing.

    Fix: the engine is reachable here through ``conftest.tmp_nous_home``
    and one ``tick()`` call lands a non-zero tick counter and a
    forward-moving timestamp. The end-of-tick finiteness guard in
    ``engine._assert_post_tick_finite`` makes a NaN-poisoned tick raise
    rather than return a corrupt context.
    """

    def test_single_tick_advances_state(self, tmp_nous_home: Path) -> None:
        from nous.engine import Engine

        engine = Engine()
        engine.start()
        try:
            before = engine.state.tick
            ctx = engine.tick()
            assert ctx.tick == before + 1
            assert ctx.ts_s > 0.0
            assert ctx.dt_s > 0.0
        finally:
            engine.stop()
