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
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl

from nous.anthropic_client import CallCap
from nous.audit import redact
from nous.auth.oauth import FileOAuthProvider
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
