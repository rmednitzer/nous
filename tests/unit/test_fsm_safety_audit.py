"""Engine wiring for the ADR 0022 runtime safety enforcer.

The FSM safety gates route through the engine's shared
:class:`~nous.safety.SafetyEnforcer`. This file pins the three things the
wiring PR adds on top of the gate logic itself (covered in
``test_state_machine_guards``): the per-constraint violation counter the
engine exposes for ``device_info``, the ``Tier.SAFETY`` audit records a
gated transition mirrors, and the fact that those records leave the audit
hash chain intact.
"""

from __future__ import annotations

import json
from pathlib import Path

from nous.audit import AuditLogger, verify_chain
from nous.engine import Engine
from nous.policy import Tier
from nous.state.machine import Mode


def _idle_engine(tmp_path: Path) -> tuple[Engine, str]:
    log_path = str(tmp_path / "audit.jsonl")
    eng = Engine(audit=AuditLogger(log_path))
    eng.start()
    eng.request_transition("ready")
    assert eng.fsm.current is Mode.IDLE
    return eng, log_path


def _safety_records(log_path: str) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    with open(log_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("tier") == int(Tier.SAFETY):
                out.append(rec)
    return out


def test_refused_transition_increments_posture(tmp_nous_home: Path) -> None:
    eng, _ = _idle_engine(tmp_nous_home)
    ok, mode, _reason = eng.request_transition(
        "mission",
        context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert not ok
    assert mode is Mode.IDLE
    posture = eng.safety.posture()
    assert posture["total_violations"] == 1
    assert posture["by_constraint"]["SC-2"] == 1
    assert posture["registered"] == ["SC-2", "SC-8"]


def test_refused_transition_writes_safety_audit_record(tmp_nous_home: Path) -> None:
    eng, log_path = _idle_engine(tmp_nous_home)
    eng.request_transition(
        "mission",
        context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
    )
    records = _safety_records(log_path)
    assert len(records) == 1
    rec = records[0]
    assert rec["denied"] is True
    assert rec["tool"] == "state_transition"
    safety = rec["safety"]
    assert isinstance(safety, dict)
    assert safety["constraint_id"] == "SC-2"
    assert safety["approved"] is False
    assert safety["violation_type"] == "refused"


def test_admitted_transition_mirrors_every_gate(tmp_nous_home: Path) -> None:
    eng, log_path = _idle_engine(tmp_nous_home)
    ok, mode, _ = eng.request_transition(
        "mission",
        context={"thermal_headroom_c": 20.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert ok and mode is Mode.MISSION
    records = _safety_records(log_path)
    # Both gates pass on an admitted entry, so both are mirrored approved.
    constraints = sorted(str(r["safety"]["constraint_id"]) for r in records)  # type: ignore[index]
    assert constraints == ["SC-2", "SC-8"]
    assert all(r["denied"] is False for r in records)


def test_safety_records_preserve_audit_chain(tmp_nous_home: Path) -> None:
    eng, log_path = _idle_engine(tmp_nous_home)
    eng.request_transition(
        "mission",
        context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
    )
    eng.request_transition(
        "mission",
        context={"thermal_headroom_c": 20.0, "thermal_headroom_threshold_c": 5.0},
    )
    report = verify_chain(log_path)
    assert report["ok"] is True
    assert report["chained"] >= 3


def test_safety_evidence_is_sanitised(tmp_nous_home: Path) -> None:
    # Non-finite context is stringified (strict JSON for off-host verifiers)
    # and secret-like keys are redacted, the same allowlist the runner applies
    # to tool args. A non-finite candidate also fails the gate closed.
    eng, log_path = _idle_engine(tmp_nous_home)
    ok, _, _ = eng.request_transition(
        "mission",
        context={
            "thermal_headroom_c": float("nan"),
            "thermal_headroom_threshold_c": 5.0,
            "authorization": "Bearer super-secret",
        },
    )
    assert not ok
    raw = Path(log_path).read_text(encoding="utf-8")
    # No bare NaN/Infinity tokens: every audit line must parse as strict JSON.
    assert "NaN" not in raw
    assert "Infinity" not in raw
    records = _safety_records(log_path)
    evidence = records[0]["safety"]["evidence"]  # type: ignore[index]
    assert evidence["thermal_headroom_c"] == "nan"
    assert evidence["authorization"] == "<REDACTED>"


def test_pure_python_engine_has_no_audit_sink(tmp_nous_home: Path) -> None:
    # Without an AuditLogger the safety mirror is a no-op; the gate logic
    # and the posture counter still work (the SQLite transition log and the
    # enforcer counters do not depend on the audit sink).
    eng = Engine()
    eng.start()
    eng.request_transition("ready")
    ok, _, _ = eng.request_transition(
        "mission",
        context={"thermal_headroom_c": 1.0, "thermal_headroom_threshold_c": 5.0},
    )
    assert not ok
    assert eng.audit is None
    assert eng.safety.violation_count("SC-2") == 1
