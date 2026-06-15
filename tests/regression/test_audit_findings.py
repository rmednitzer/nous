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
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl

from nous.anthropic_client import CallCap, CapExhausted
from nous.audit import AuditLogger, AuditRecord, redact, verify_chain
from nous.auth.oauth import FileOAuthProvider
from nous.config import Settings
from nous.estimators.biometrics import BiometricsKalman
from nous.estimators.compute import ComputeKalman
from nous.estimators.sensors import EnvironmentalKalman
from nous.estimators.storage import StorageKalman
from nous.estimators.thermal import ThermalKalman
from nous.interop.cot import CotAdapter
from nous.interop.misb_klv import MisbKlvAdapter
from nous.types import Observation


def _oauth_client(client_id: str = "c-1") -> OAuthClientInformationFull:
    return OAuthClientInformationFull(
        client_id=client_id,
        client_secret="s",
        redirect_uris=[AnyHttpUrl("https://example.com/cb")],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp:tools",
    )


def _build_provider(tmp_path: Path) -> FileOAuthProvider:
    return FileOAuthProvider(
        tmp_path / "auth",
        single_client=True,
        access_ttl=3600,
        refresh_ttl=86_400,
        code_ttl=60,
    )


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
    while the flock is still held, and an ``OSError`` from fsync raises an
    error (``CapPersistError`` since ADR 0056) instead of returning a success
    the caller cannot rely on.
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


class TestCap1PeekAgreesWithIncrement:
    """CAP-1: the status read must not advertise a slot the spend path denies.

    Original defect (``docs/audit-2026-06-14.md`` CAP-1): ``CallCap.peek``,
    which feeds ``anthropic_cap_status``, failed open on a corrupt counter
    (returning ``count=0`` so the tool reported the cap healthy and
    available), while ``CallCap.increment`` failed closed on the same file
    by raising ``CapExhausted``. A controller polling the status tool was
    therefore told a cloud call would succeed at the instant every
    ``inference_cloud`` call was being silently downgraded to the local
    mock. A second, smaller drift: increment leaked a raw ``ValueError`` on
    a non-integer ``count`` instead of ``CapExhausted``.

    Fix (ADR 0049): both readers parse through one ``_parse_count`` helper.
    A counter that makes increment refuse now makes peek report
    ``corrupt=True`` (and the status tool report unavailable/exhausted), and
    increment fails closed on a corrupt or spent counter with ``CapExhausted``
    (ADR 0056 later split the fsync-durability fault off as ``CapPersistError``).
    """

    @pytest.mark.parametrize(
        "raw",
        [
            "not valid json",
            '{"date": "REPLACE", "count": "lots"}',
            '{"date": "REPLACE", "count": [1, 2]}',
            '{"date": "REPLACE", "count": -5}',
            '{"date": "REPLACE", "count": 0.5}',
            '{"date": "REPLACE", "count": true}',
        ],
    )
    def test_corrupt_counter_refused_and_reported_corrupt(
        self, tmp_path: Path, raw: str
    ) -> None:
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        path = tmp_path / "count"
        path.write_text(raw.replace("REPLACE", today), encoding="utf-8")

        assert CallCap(path, cap=5).peek().corrupt is True
        with pytest.raises(CapExhausted):
            CallCap(path, cap=5).increment()

    def test_intact_counter_reported_not_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "count"
        cap = CallCap(path, cap=5)
        cap.increment()
        reading = cap.peek()
        assert reading.corrupt is False
        assert reading.count == 1


class TestAud1ChainHeadTracksOnDiskTail:
    """AUD-1: the chain head follows the on-disk tail, not the fsync.

    Original finding (``docs/audit-2026-06-14.md`` AUD-1): ``write`` advanced
    ``_chain_head`` right after the emit and only then polled for a silent
    fsync failure, which read as "advance the head before the record is
    durable". The proposed remediation -- gate the head advance on a clean
    fsync -- would corrupt the chain rather than fix it: ``_FsyncingFileHandler``
    writes the line into the append-only file before it fsyncs, so an
    fsync-failed record is physically present, and a later record that linked
    to the prior durable line instead would skip it and break ``verify_chain``.

    Invariant (ADR 0050): the head advances for every emitted record (the
    on-disk tail), while durability is tracked separately via ``degraded`` /
    ``fsync_failures`` / ``writes_total``. These tests pin it, and they fail if
    a future change gates the head advance on a clean fsync.
    """

    def test_chain_verifies_across_a_silent_fsync_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "audit.jsonl"
        logger = AuditLogger(path)
        logger.write(AuditRecord.from_output(tool="a", tier=0, args={}, output="1"))

        real_fsync = os.fsync
        calls = {"n": 0}

        def _fail_once(fd: int) -> None:
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("simulated fsync failure")
            real_fsync(fd)

        monkeypatch.setattr("nous.audit.os.fsync", _fail_once)
        logger.write(AuditRecord.from_output(tool="b", tier=0, args={}, output="2"))
        assert logger.degraded is True  # the fsync failure is observable

        logger.write(AuditRecord.from_output(tool="c", tier=0, args={}, output="3"))

        report = verify_chain(path)
        assert report["ok"] is True, report
        assert report["chained"] == 3

    def test_fsync_failure_advances_head_but_holds_writes_total(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "audit.jsonl"
        logger = AuditLogger(path)
        logger.write(AuditRecord.from_output(tool="a", tier=0, args={}, output="1"))
        head_after_a = logger.summary()["chain_head"]

        def _fail_fsync(fd: int) -> None:
            raise OSError("boom")

        monkeypatch.setattr("nous.audit.os.fsync", _fail_fsync)
        logger.write(AuditRecord.from_output(tool="b", tier=0, args={}, output="2"))

        # The head advanced to record b (the on-disk tail) even though its
        # fsync failed, but the durable-write counter did not move.
        assert logger.summary()["chain_head"] != head_after_a
        assert logger.writes_total == 1
        assert logger.degraded is True


class TestC2RedactionRecurses:
    """C2: argument redaction must walk nested mappings and lists.

    Original defect (``AUDIT.md`` C2, 2026-05-20): ``redact()`` walked
    only the top-level keys of the argument mapping. A caller that
    passed ``{"context": {"headers": {"Authorization": "Bearer ..."}}}``
    wrote the secret to the audit log verbatim, because the regex only
    inspected the outermost key. The MCP tool surface accepted only
    flat scalars at the time, so the blast radius was bounded, but any
    tool that accepted structured payloads (BL-014 scenario loader,
    BL-041 interop encoders) would have leaked.

    Fix: ``redact()`` now recurses through nested mappings and list
    items; the redaction allowlist applies at every depth. Oversize
    strings are truncated at every depth too, so a buried megabyte
    cannot inflate the audit line.
    """

    def test_nested_mapping_keys_are_redacted(self) -> None:
        out = redact(
            {"context": {"headers": {"Authorization": "Bearer xyz"}}}
        )
        assert out["context"]["headers"]["Authorization"] == "<REDACTED>"

    def test_list_of_mappings_is_redacted(self) -> None:
        out = redact(
            {"items": [{"password": "p1"}, {"command": "ls"}]}
        )
        assert out["items"][0]["password"] == "<REDACTED>"
        assert out["items"][1]["command"] == "ls"

    def test_top_level_still_redacted(self) -> None:
        out = redact({"token": "abc", "command": "ls"})
        assert out["token"] == "<REDACTED>"
        assert out["command"] == "ls"

    def test_oversize_nested_string_is_truncated(self) -> None:
        large = "x" * 5000
        out = redact({"nested": {"payload": large}})
        truncated = out["nested"]["payload"]
        assert truncated.startswith("x" * 4096)
        assert "<truncated 5000>" in truncated


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
        # AUDIT-2026-05-24 N7: decoder returns UTF-8 strings (with
        # hex fallback for non-UTF-8 bytes); the legacy hex-on-every-
        # value pattern is gone. Round trip is symmetric for the
        # str-encoded values the encoder writes.
        assert decoded["items"][5] == "x" * 500


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

    def test_decoder_refuses_doctype_past_512_bytes(self) -> None:
        """AUDIT-2026-06-13 1-A: the DOCTYPE guard scanned only the first
        512 bytes, so a declaration placed after a long, well-formed comment
        reached the parser. The guard now scans the whole payload."""
        adapter = CotAdapter()
        padding = b"<!-- " + b"x" * 600 + b" -->"
        malicious = padding + b"<!DOCTYPE event SYSTEM 'http://evil'><event/>"
        assert len(padding) > 512
        decoded = adapter.decode(malicious)
        assert "error" in decoded


class TestH6OAuthFileStoreLockedAndConfidential:
    """H6: OAuth file store needs an async lock plus ``chmod 0600`` plus
    parent-dir fsync.

    Original defect (``AUDIT.md`` H6, 2026-05-20): ``_Store.save``
    wrote atomically (tmp + replace) but did not fsync the parent
    directory and did not enforce the file mode. Concurrent FastMCP
    requests could interleave ``_Store.load() ... _Store.save()``
    because no lock arbitrated the read-modify-write cycle of token
    / client / code state. Under single-client lockdown the risk
    was bounded; under multi-tenant L3 it becomes a real race.

    Fix: ``FileOAuthProvider`` carries an ``asyncio.Lock``; every
    public RMW method wraps its sequence under it. ``_Store.save``
    chmods the file to ``0o600`` before and after the rename and
    fsyncs the parent directory so the rename hits stable storage.
    """

    def test_state_files_end_at_mode_0600(self, tmp_path: Path) -> None:
        import asyncio

        provider = _build_provider(tmp_path)
        asyncio.run(provider.register_client(_oauth_client()))
        provider._issue("c-1", ["mcp:tools"])

        for name in ("clients.json", "tokens.json"):
            path = tmp_path / "auth" / name
            assert path.exists(), name
            mode = path.stat().st_mode & 0o777
            assert mode == 0o600, f"{name} mode {oct(mode)} != 0o600"

    def test_provider_carries_an_async_lock(self, tmp_path: Path) -> None:
        import asyncio

        provider = _build_provider(tmp_path)
        assert isinstance(provider._async_lock, asyncio.Lock)


class TestH7RefreshTokenReuseRevokesFamily:
    """H7: refresh-token reuse must revoke the entire family.

    Original defect (``AUDIT.md`` H7, 2026-05-20):
    ``exchange_refresh_token`` deleted the consumed refresh token and
    issued a fresh pair but left any parallel refresh tokens issued
    earlier in the chain alive. If an attacker captured a refresh
    token and the rightful client then used it, the attacker's
    parallel chain continued to mint access tokens silently.

    Fix: every refresh-token record carries an ``issue_id`` naming
    its family. Rotation propagates the id; the consumed record is
    marked ``consumed=True`` instead of popped so reuse stays
    detectable. ``load_refresh_token`` and ``exchange_refresh_token``
    fire family revocation on a consumed-token presentation, per
    OAuth 2.1 BCP §4.13.
    """

    def test_rotated_pair_inherits_family_id(self, tmp_path: Path) -> None:
        import asyncio

        provider = _build_provider(tmp_path)
        pair_1 = provider._issue("c-1", ["mcp:tools"])
        refresh_1 = asyncio.run(
            provider.load_refresh_token(_oauth_client(), pair_1.refresh_token or "")
        )
        assert refresh_1 is not None
        pair_2 = asyncio.run(
            provider.exchange_refresh_token(_oauth_client(), refresh_1, ["mcp:tools"])
        )
        tokens = provider._tokens.load()
        original = tokens["refresh:" + (pair_1.refresh_token or "")]["issue_id"]
        rotated = tokens["refresh:" + (pair_2.refresh_token or "")]["issue_id"]
        assert original == rotated

    def test_reuse_revokes_rotated_access_token(self, tmp_path: Path) -> None:
        import asyncio

        provider = _build_provider(tmp_path)
        pair_1 = provider._issue("c-1", ["mcp:tools"])
        refresh_1 = asyncio.run(
            provider.load_refresh_token(_oauth_client(), pair_1.refresh_token or "")
        )
        assert refresh_1 is not None
        pair_2 = asyncio.run(
            provider.exchange_refresh_token(_oauth_client(), refresh_1, ["mcp:tools"])
        )
        assert (
            asyncio.run(provider.load_access_token(pair_2.access_token)) is not None
        )

        # Replay the consumed refresh; family revocation fires.
        assert (
            asyncio.run(
                provider.load_refresh_token(
                    _oauth_client(), pair_1.refresh_token or ""
                )
            )
            is None
        )
        assert asyncio.run(provider.load_access_token(pair_2.access_token)) is None


class TestM1RunnerDenialStampsExitCode:
    """M1: runner denial record must carry ``exit_code`` for machine queries.

    Original defect (``AUDIT.md`` M1, 2026-05-20): the denial branch of
    ``runner.run`` wrote ``denied=True`` and ``decision_reason=...`` but
    left ``exit_code=None``. Counting denials per tier per day required
    parsing the body string ``[DENIED tier N (NAME): reason]`` rather
    than filtering on a typed field, which is brittle and costly at log
    volume.

    Fix: ``runner.run`` now passes ``exit_code=1`` on the denial path.
    The success path keeps ``exit_code=None`` (no abnormal exit), so a
    JSONL consumer can split on ``exit_code is not None`` to bucket
    denials and worker errors apart from normal returns.
    """

    def test_denial_record_carries_exit_code_one(self, tmp_path: Path) -> None:
        import asyncio

        from nous.audit import AuditLogger
        from nous.policy import PolicyMode
        from nous.runner import run

        audit_path = tmp_path / "audit.jsonl"
        audit = AuditLogger(audit_path)

        async def _work() -> str:
            return "should-not-run"

        body = asyncio.run(
            run(
                tool="state_transition",
                args={"to": "mission"},
                work=_work,
                audit=audit,
                policy_mode=PolicyMode.READONLY,
            )
        )
        audit.flush()

        assert body.startswith("[DENIED")
        lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        record = json.loads(lines[-1])
        assert record["denied"] is True
        assert record["exit_code"] == 1

    def test_success_record_leaves_exit_code_unset(self, tmp_path: Path) -> None:
        import asyncio

        from nous.audit import AuditLogger
        from nous.policy import PolicyMode
        from nous.runner import run

        audit_path = tmp_path / "audit.jsonl"
        audit = AuditLogger(audit_path)

        async def _work() -> str:
            return "ok"

        asyncio.run(
            run(
                tool="device_info",
                args={},
                work=_work,
                audit=audit,
                policy_mode=PolicyMode.READONLY,
            )
        )
        audit.flush()

        record = json.loads(audit_path.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert record.get("denied", False) is False
        assert record.get("exit_code") is None


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


class TestM10ProfileLoaderValidatesAtLoadTime:
    """M10: profile YAML must be schema-validated when the engine loads it.

    Original defect (``AUDIT.md`` M10, 2026-05-20): ``engine._load_profile``
    fell back to ``{"name": name, "source": "default-fallback"}`` whenever
    the YAML was missing, malformed, or did not deserialise to a mapping.
    ``scripts/gen_schemas.py`` output was not consumed at load time, so a
    typo in a profile key silently degraded to the default and an operator
    only noticed when a subsystem behaved out of spec. BL-006 closed this
    by wiring ``ProfileModel.model_validate(data)`` into the loader and
    raising ``ValueError`` on any schema mismatch.

    Fix: every load path now fails fast. The behaviour is fully covered
    by ``tests/unit/test_engine_profile_loading.py``; this class pins
    the closure inside the regression suite per ADR 0023.
    """

    def test_profile_model_rejects_missing_name(self) -> None:
        from pydantic import ValidationError

        from nous.engine import ProfileModel

        with pytest.raises(ValidationError):
            ProfileModel.model_validate({"power": {"battery_wh": 100}})

    def test_loader_raises_on_missing_file(self) -> None:
        from nous.engine import _load_profile

        with pytest.raises(FileNotFoundError, match="profile YAML not found"):
            _load_profile("regression-profile-does-not-exist")


class TestN7MisbKlvDecodeReturnsSymmetricTypes:
    """N7: MISB KLV decoder must return UTF-8 strings (with hex fallback).

    Original defect (``AUDIT.md`` N7, 2026-05-24): the decoder
    returned ``{k: v.hex() for k, v in items.items()}``, so every
    value came back as a hex string regardless of how the encoder
    serialised it. The encoder writes ``str(v).encode("utf-8")``
    for every non-timestamp key; the round trip was therefore
    lossy by design (encoder writes ``b"foo"``, decoder yields
    ``"666f6f"``).

    Fix: the decoder calls ``_decode_value`` per item. The
    timestamp key (2) returns an ``int`` (microseconds since
    Unix epoch per MISB ST 0601). Every other key attempts
    UTF-8 decode and falls back to hex if the bytes are not
    valid UTF-8. Round trip is symmetric for the str-encoded
    values the encoder writes; binary-key edge cases stay
    inspectable as hex.
    """

    def test_round_trip_returns_utf8_string(self) -> None:
        adapter = MisbKlvAdapter(max_value_len=4096)
        payload = adapter.encode({"ts_s": _now(), "5": "hello"})
        decoded = adapter.decode(payload)
        assert decoded["items"][5] == "hello"

    def test_timestamp_key_returns_microseconds_int(self) -> None:
        adapter = MisbKlvAdapter()
        ts = _now()
        payload = adapter.encode({"ts_s": ts, "3": "ok"})
        decoded = adapter.decode(payload)
        # Key 2 is the timestamp; the encoder writes microseconds
        # since Unix epoch as 8 raw bytes big-endian.
        assert isinstance(decoded["items"][2], int)
        assert decoded["items"][2] == int(ts * 1_000_000)

    def test_non_utf8_bytes_fall_back_to_hex(self) -> None:
        from nous.interop.misb_klv import _decode_value

        # Construct a value that is not valid UTF-8 (a lone
        # continuation byte).
        bad = b"\xc3\x28"
        result = _decode_value(5, bad)
        assert result == bad.hex()


class TestN2AuditSinkRecoversInProcess:
    """N2: a degraded audit sink must recover without a process restart.

    Original defect (``docs/audit-2026-05-23.md`` N2): the live
    VM was observed in the ``audit.degraded=true`` state. The
    ``AuditLogger`` only opened its sink once, in ``__init__``,
    so an operator who remediated the underlying filesystem
    issue (permissions, mount, ``ReadWritePaths=`` drift) had to
    restart ``nous.service`` to clear the degraded flag. The
    restart itself dropped any in-flight audit records.

    Fix: ``AuditLogger.resync()`` re-runs the sink-opening
    logic in place. The new ``audit_resync`` MCP tool (T2)
    exposes the same path to a controller. ``fsync_failures``
    stays cumulative so the operator can still see the loss
    window. ``recovered`` distinguishes the "this call cleared
    the degraded state" path from the "sink was already healthy"
    no-op.
    """

    def test_resync_recovers_from_degraded(self, tmp_path: Path) -> None:
        from nous.audit import AuditLogger

        logger = AuditLogger(Path("/proc/0/audit.jsonl"))
        assert logger.degraded

        logger.path = str(tmp_path / "audit.jsonl")
        result = logger.resync()
        assert result["recovered"] is True
        assert result["degraded"] is False

    def test_audit_resync_tool_is_classified_stateful(self) -> None:
        from nous.policy import Tier, classify

        tier, _ = classify("audit_resync", {})
        assert tier is Tier.STATEFUL


class TestComms1OutboxSurvivesDeniedLink:
    """COMMS-1: outbound traffic must survive a degraded or denied link.

    Original defect (``docs/audit-2026-06-14.md`` COMMS-1): the comms
    send seam was fire-and-forget. ``CommsSubsystem.tx`` accepts bytes
    only on a live link, so ``comms_send`` / ``comms_publish`` /
    ``self_model_publish`` on an aged-out, forced-down, or unknown link
    returned ``bytes_accepted: 0`` and the message was gone, with no
    queue, no retry, and no triage. Validated on the live twin: a
    ``comms_publish`` of a CoT event on a denied link encoded a full
    352-byte message and then dropped it.

    Fix: a bounded, precedence-ordered store-and-forward outbox
    (``state/comms_outbox.py``, BL-077 / ADR 0047) holds the package and
    the engine tick drains it in triage order as the link recovers. A
    package is only ever evicted to make room for a strictly
    higher-precedence one, and an expired package is dropped rather than
    shipped stale.
    """

    def test_package_queued_on_denied_link_survives_recovery(self) -> None:
        from nous.state.comms_outbox import CommsOutbox, Precedence
        from nous.subsystems.comms import CommsSubsystem

        comms = CommsSubsystem(
            {"comms": {"links": [{"id": "tak", "bandwidth_bps": 500_000, "max_age_s": 60}]}}
        )
        comms.set_link_state("tak", connected=False)
        outbox = CommsOutbox()

        outbox.enqueue("tak", 352, now_s=0.0, precedence=Precedence.IMMEDIATE)
        deferred = outbox.flush(comms, now_s=1.0)
        assert deferred.delivered == []
        assert outbox.depth() == 1  # held, not dropped

        comms.clear_link_override("tak")
        recovered = outbox.flush(comms, now_s=2.0)
        assert len(recovered.delivered) == 1
        assert outbox.depth() == 0

    def test_outbox_tools_are_classified(self) -> None:
        from nous.policy import Tier, classify

        assert classify("comms_outbox", {})[0] is Tier.READ_ONLY
        assert classify("comms_enqueue", {})[0] is Tier.STATEFUL
        assert classify("comms_flush", {})[0] is Tier.STATEFUL


class TestRun1CaughtErrorStampsExitCode:
    """RUN-1: a caught worker error must be distinguishable in the audit record.

    Original defect (``docs/audit-2026-06-14.md`` RUN-1): the M1 fix stamped
    ``exit_code=1`` on the policy-denial path and its docstring framed the
    intent as "a consumer splits on ``exit_code is not None`` to bucket denials
    and worker errors apart from normal returns". But the runner's
    caught-exception path wrote the audit record with ``exit_code`` defaulting
    to ``None``, identical to a normal return, so a caught worker error was
    indistinguishable from a clean return on the typed field.

    Fix (ADR 0048): the exception path now stamps ``exit_code=1``. The contract
    is two-valued: ``None`` is a normal return, ``1`` is any abnormal outcome,
    and ``denied`` separates a policy refusal from a caught error.
    """

    def test_caught_error_is_exit_code_one_and_not_denied(self, tmp_path: Path) -> None:
        import asyncio

        from nous.audit import AuditLogger
        from nous.policy import PolicyMode
        from nous.runner import run

        audit = AuditLogger(tmp_path / "audit.jsonl")

        async def _raises() -> str:
            raise RuntimeError("boom")

        body = asyncio.run(
            run(
                tool="device_info",
                args={},
                work=_raises,
                audit=audit,
                policy_mode=PolicyMode.OPEN,
            )
        )
        # Body is the class name only since ADR 0055; the message is redacted.
        assert body == "[error RuntimeError]"
        audit.flush()
        record = json.loads(
            Path(audit.path).read_text(encoding="utf-8").strip().splitlines()[-1]
        )
        assert record["exit_code"] == 1
        assert record["denied"] is False

    def test_normal_return_keeps_exit_code_none(self, tmp_path: Path) -> None:
        import asyncio

        from nous.audit import AuditLogger
        from nous.policy import PolicyMode
        from nous.runner import run

        audit = AuditLogger(tmp_path / "audit.jsonl")

        async def _ok() -> str:
            return "ok"

        asyncio.run(
            run(
                tool="device_info",
                args={},
                work=_ok,
                audit=audit,
                policy_mode=PolicyMode.OPEN,
            )
        )
        audit.flush()
        record = json.loads(
            Path(audit.path).read_text(encoding="utf-8").strip().splitlines()[-1]
        )
        assert record.get("exit_code") is None
        assert record["denied"] is False


class TestHigh1RunnerRedactsCaughtExceptionBody:
    """HIGH-1: a caught worker error must not return its message to the caller.

    Original defect (``docs/audit-2026-06-14b.md`` HIGH-1): the runner's
    caught-exception body was ``f"[error {cls}: {exc}]"``, the raw ``str(exc)``
    truncated but never redacted, and that body is returned to the MCP caller.
    A backend failure on a read-only call (``state_get`` / ``state_history``
    reach the database) raises an exception whose message can embed the
    ``NOUS_DB_URL`` data source: host, user, and password. So an admitted
    read-only caller could read a credential out of an error body.

    Fix (ADR 0055): the body carries only the exception class; the full detail
    goes to stderr. The ADR 0048 ``exit_code=1`` / ``denied=False`` contract is
    unchanged.
    """

    def test_credential_shaped_message_does_not_reach_the_caller(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        import asyncio

        from nous.audit import AuditLogger
        from nous.policy import PolicyMode
        from nous.runner import run

        audit = AuditLogger(tmp_path / "audit.jsonl")
        secret = "postgresql://nous:hunter2@db.internal:5432/nous"

        async def _raises() -> str:
            raise RuntimeError(f"could not connect: {secret}")

        body = asyncio.run(
            run(
                tool="device_info",
                args={},
                work=_raises,
                audit=audit,
                policy_mode=PolicyMode.READONLY,
            )
        )
        # The secret, the URL, and the message never reach the caller.
        assert "hunter2" not in body
        assert secret not in body
        assert "could not connect" not in body
        # The class name survives, enough to route to the right *_status read.
        assert body == "[error RuntimeError]"
        # The full detail is on stderr for an operator with host access.
        assert secret in capsys.readouterr().err
        # The ADR 0048 typed contract is intact: abnormal, not a denial.
        audit.flush()
        record = json.loads(
            Path(audit.path).read_text(encoding="utf-8").strip().splitlines()[-1]
        )
        assert record["exit_code"] == 1
        assert record["denied"] is False


class TestH1CommsTxRejectsZeroCapacityLink:
    """H-1: a transmission on a zero-capacity link must be rejected, not accepted.

    Original defect (``docs/audit-2026-06-14b.md`` H-1): the BL-048 capacity cap
    let ``CommsSubsystem.tx`` return ``n_bytes`` accepted on a propagation link
    driven below its SNR floor (``capacity_bps == 0``) while stamping
    ``throughput_bps=0``, so a direct ``comms_send`` or an outbox flush on a
    fully-degraded but still-live link reported success on a link that carries
    nothing.

    Fix (BL-091): ``tx`` gates ``capacity_bps <= 0`` to ``return 0`` and stamps
    the zero rate without resetting the age-out timer, matching the forced-down
    guard.
    """

    def test_tx_rejects_and_stamps_zero_rate(self) -> None:
        from collections.abc import Mapping

        from nous.subsystems.comms import CommsSubsystem

        link: Mapping[str, Any] = {
            "id": "relay",
            "bandwidth_bps": 2_000_000,
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
        comms = CommsSubsystem(
            {"comms": {"links": [link]}}, position_fn=lambda: (47.0, 13.30, 500.0)
        )
        comms.step(1.0)
        relay = comms.link("relay")
        assert relay is not None
        assert relay.is_live() is True
        assert relay.capacity_bps == 0.0
        assert comms.tx("relay", 1500) == 0
        assert relay.throughput_bps == 0.0
        # A rejected send does not reset the age-out timer.
        assert relay.age_s > 0.0


class TestH2CommsEstimatorRefreshesMissingLink:
    """H-2: a link absent from the observation is refreshed each update, not frozen.

    Original defect (``docs/audit-2026-06-14b.md`` H-2):
    ``CommsParticleFilter.update`` refreshed a link absent from the current
    observation with ``setdefault``, so after the first absence its
    ``LinkEstimate`` froze while its particle belief kept drifting under
    ``predict()``. Latent through the engine because ``sensor_obs`` always emits
    every link, but a correctness defect.

    Fix (BL-091): the missing-link branch assigns unconditionally, so the
    estimate always reflects the current belief.
    """

    def test_missing_link_estimate_tracks_the_drifted_belief(self) -> None:
        import numpy as np

        from nous.estimators.comms import CommsParticleFilter
        from nous.types import Observation

        def obs(*links: dict[str, float | bool | str]) -> Observation:
            return Observation(
                source="comms", ts_s=1.0, payload={"links": list(links)}, noise={}
            )

        f = CommsParticleFilter()
        f.update(
            obs(
                {
                    "link_id": "lte",
                    "rssi_dbm": -70.0,
                    "loss_pct": 1.0,
                    "throughput_bps": 1_000_000.0,
                    "connected": True,
                }
            )
        )
        assert f.links()[0].connected is True
        other: dict[str, float | bool | str] = {
            "link_id": "other",
            "rssi_dbm": -70.0,
            "loss_pct": 1.0,
            "throughput_bps": 500_000.0,
            "connected": True,
        }
        f.update(obs(other))  # first absence of lte
        f._links["lte"].particles = np.zeros_like(f._links["lte"].particles)
        f.update(obs(other))  # a second absence must refresh, not freeze
        lte = next(e for e in f.links() if e.link_id == "lte")
        assert lte.connected is False


class TestM1CommsEstimateCarriesBandwidth:
    """M-1: the filter's LinkEstimate carries the rated bandwidth for health.

    Original defect (``docs/audit-2026-06-14b.md`` M-1):
    ``_link_estimate_from_belief`` never set ``bandwidth_bps``, so an
    estimator-produced ``LinkEstimate`` fell back to the legacy flat throughput
    floor in ``comms_state._rate_healthy`` rather than the per-link capacity
    fraction. The FSM-facing ``derive_state`` uses the subsystem estimates that
    carry it, so this was the informational estimator read only.

    Fix (BL-091): the rated bandwidth is threaded from ``sensor_obs`` through the
    belief to the estimate.
    """

    def test_estimate_carries_bandwidth_from_observation(self) -> None:
        from nous.estimators.comms import CommsParticleFilter
        from nous.types import Observation

        f = CommsParticleFilter()
        f.update(
            Observation(
                source="comms",
                ts_s=1.0,
                noise={},
                payload={
                    "links": [
                        {
                            "link_id": "relay",
                            "rssi_dbm": -70.0,
                            "loss_pct": 1.0,
                            "throughput_bps": 1_000_000.0,
                            "capacity_bps": 1_500_000.0,
                            "bandwidth_bps": 2_000_000.0,
                            "connected": True,
                        }
                    ]
                },
            )
        )
        assert f.links()[0].bandwidth_bps == 2_000_000.0


class TestM2CommsLikelihoodFloorBoundary:
    """M-2: a throughput exactly at the 1 bps floor is processed, not floored.

    Original defect (``docs/audit-2026-06-14b.md`` M-2):
    ``_likelihood_given_connected`` early-returned the likelihood floor at
    ``throughput <= _THROUGHPUT_FLOOR_BPS``, treating a link exactly at the 1 bps
    floor as disconnected, inconsistent with the ``>=`` floor liveness boundary
    in ``_link_estimate_from_belief``.

    Fix (BL-091): the comparison is ``<``, so a link exactly at the floor is
    processed; strictly below still returns the likelihood floor.
    """

    def test_floor_boundary_is_strict(self) -> None:
        from nous.estimators.comms import (
            _LIKELIHOOD_FLOOR,
            _THROUGHPUT_FLOOR_BPS,
            _likelihood_given_connected,
        )

        at_floor = _likelihood_given_connected(
            _THROUGHPUT_FLOOR_BPS, _THROUGHPUT_FLOOR_BPS, 0.0, True
        )
        below = _likelihood_given_connected(
            _THROUGHPUT_FLOOR_BPS - 0.1, _THROUGHPUT_FLOOR_BPS, 0.0, True
        )
        assert at_floor > _LIKELIHOOD_FLOOR
        assert below == _LIKELIHOOD_FLOOR


class TestMed1InferenceCloudReusesOneClient:
    """MED-1: inference_cloud must reuse one Anthropic client, not build per call.

    Original defect (``docs/audit-2026-06-14b.md`` MED-1): ``inference_cloud``
    constructed a fresh ``AnthropicClient`` inside its per-call ``_work`` body,
    so every call built a new ``AsyncAnthropic`` (a new httpx pool) and discarded
    the previous client's ``last_cache_read_input_tokens``, the metric that makes
    the prompt-cache discipline observable.

    Fix (ADR 0056): ``Nous`` caches one client via a ``cached_property`` built
    from its own settings, and ``inference_cloud`` reads ``app.anthropic_client``.
    """

    def test_app_caches_one_client_from_its_settings(self, config: Settings) -> None:
        from nous.anthropic_client import AnthropicClient
        from nous.server import build_app

        app = build_app(config)
        first = app.anthropic_client
        second = app.anthropic_client
        assert isinstance(first, AnthropicClient)
        assert first is second  # cached, not rebuilt per access
        # Built from the app's settings, not the global get_settings().
        assert first.settings is config


class TestLow3CapPersistErrorIsDistinctFromExhaustion:
    """LOW-3: an fsync durability failure must not read as cap exhaustion.

    Original defect (``docs/audit-2026-06-14b.md`` LOW-3): ``CallCap.increment``
    raised ``CapExhausted`` on an ``os.fsync`` ``OSError``, so a transient
    durability fault surfaced through the fallback ladder as a spent budget
    (``reason: "cap exhausted"``).

    Fix (ADR 0056): the fsync path raises ``CapPersistError``, independent of
    ``CapExhausted`` (so a cap-exhausted handler does not swallow it), and the
    spend path still fails closed.
    """

    def test_fsync_failure_raises_a_distinct_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nous.anthropic_client import CallCap, CapExhausted, CapPersistError

        def _fail_fsync(_fd: int) -> None:
            raise OSError("simulated fsync failure")

        monkeypatch.setattr("nous.anthropic_client.os.fsync", _fail_fsync)
        with pytest.raises(CapPersistError):
            CallCap(tmp_path / "cap.json", cap=5).increment()
        assert not issubclass(CapPersistError, CapExhausted)


class TestMed2TickAdvanceCountIsHonest:
    """MED-2: tick_advance must not report ``n`` as the net engine advance.

    Original defect (``docs/audit-2026-06-14b.md`` MED-2): the tool returned
    ``ticks_advanced=n``, but the concurrent tick loop can fire ``engine.tick()``
    during the periodic checkpoint yield, so the engine's ``tick`` / ``ts_s``
    advanced by more than ``n``. A caller computing ``start_ts + n*dt`` then
    disagreed with the reported ``ts_s``.

    Fix (BL-093): the field is ``ticks_requested`` (the ticks this call stepped),
    and a new ``ticks_elapsed`` reports the true net engine delta, so ``ts_s`` is
    consistent with ``ticks_elapsed`` rather than with ``ticks_requested``.
    """

    async def test_loop_ticks_during_a_yield_count_as_elapsed_not_requested(
        self, config: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import anyio

        from nous.server import build_app

        app = build_app(config)
        real_checkpoint = anyio.lowlevel.checkpoint

        async def _checkpoint_that_also_ticks() -> None:
            # Simulate the background tick loop firing during the advance's yield.
            app.engine.tick()
            await real_checkpoint()

        monkeypatch.setattr(
            "nous.tools.scenarios.anyio.lowlevel.checkpoint",
            _checkpoint_that_also_ticks,
        )
        before = app.engine.state.tick
        result: Any = await app.mcp.call_tool("tick_advance", {"n": 100})
        content, _ = result
        out = json.loads(content[0].text)

        # 100 stepped here; the checkpoints at done=50 and done=100 each added a
        # tick, so the engine advanced 102 -- more than this call stepped.
        assert out["ticks_requested"] == 100
        assert out["ticks_elapsed"] == 102
        assert out["ticks_elapsed"] > out["ticks_requested"]
        assert out["tick"] == before + 102
        # ts_s tracks the true elapsed advance, not the requested count.
        assert out["ts_s"] == pytest.approx(out["tick"] * app.engine.dt_s)


class TestMed3StatusReadsRejectionsThroughHealth:
    """MED-3: a status tool reads rejected_updates via the Estimate contract.

    Original defect (``docs/audit-2026-06-14b.md`` MED-3): ``position_status`` /
    ``sensors_status`` / ``biometrics_status`` read ``est.rejected_updates`` as a
    bare attribute, but the ``Estimator`` Protocol declares only ``name`` /
    ``predict`` / ``update`` / ``state``; only three of nine estimators expose the
    attribute, so a Protocol-conforming replacement that omitted it would
    ``AttributeError`` inside the T0 read.

    Fix (ADR 0058 / ADR 0045): the tools read the count from
    ``estimate.state().health``, a Protocol-method path, and an estimator that
    reports no health block reads as zero rejections instead of raising.
    """

    async def test_status_survives_a_protocol_estimator_without_the_attribute(
        self, config: Settings
    ) -> None:
        from nous.estimators.base import Estimator
        from nous.server import build_app
        from nous.types import Estimate

        app = build_app(config)

        class _BareEstimator:
            name = "position"

            def predict(self, dt: float) -> None: ...

            def update(self, obs: object) -> None: ...

            def state(self) -> Estimate:
                return Estimate(source="position", ts_s=0.0)

        replacement = _BareEstimator()
        # Satisfies the runtime-checkable Protocol but exposes no counter.
        assert isinstance(replacement, Estimator)
        assert not hasattr(replacement, "rejected_updates")
        app.engine.position_est = replacement  # type: ignore[assignment]

        result: Any = await app.mcp.call_tool("position_status", {})
        content, _ = result
        out = json.loads(content[0].text)
        assert out["estimate"]["rejected_updates"] == 0


class TestLow4DecodeToolCoercesNonStringKeys:
    """LOW-4: interop_decode must not raise on a non-string-keyed mapping.

    Original defect (``docs/audit-2026-06-14b.md`` LOW-4): the tool passed the
    decoded mapping straight to ``json.dumps``, which raises ``TypeError`` on a
    key it cannot coerce (a tuple, or anything a future CBOR / msgpack adapter
    might produce), turning a decode call into an exception body. ``decode`` was
    typed ``Mapping[str, Any]`` but nothing enforced it.

    Fix (ADR 0058): the tool stringifies every mapping key recursively before
    ``json.dumps``, so an exotic-keyed payload decodes to valid JSON.
    """

    async def test_decode_coerces_keys_json_dumps_would_reject(
        self, config: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nous.server import build_app

        app = build_app(config)

        class _ExoticKeyAdapter:
            name = "exotic"

            def encode(self, data: Any) -> bytes:
                return b""

            def decode(self, payload: bytes) -> dict[Any, Any]:
                # A tuple key is one json.dumps rejects outright (no coercion);
                # the nested int key is the MISB-style case.
                return {("a", "b"): 1, "nested": [{3: "three"}]}

        monkeypatch.setattr(
            "nous.interop.build_adapter", lambda _name: _ExoticKeyAdapter()
        )
        result: Any = await app.mcp.call_tool(
            "interop_decode", {"adapter": "exotic", "payload_hex": ""}
        )
        content, _ = result
        out = json.loads(content[0].text)
        decoded = out["decoded"]
        assert decoded["('a', 'b')"] == 1
        assert decoded["nested"][0]["3"] == "three"
