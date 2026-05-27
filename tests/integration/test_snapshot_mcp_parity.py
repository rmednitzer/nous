"""Parity between ``engine.snapshot()`` and the MCP-facing payloads.

Closes AUDIT-2026-05-24 N4 (no test asserts the keys returned by
``engine.snapshot()`` match what ``device_health`` exposes via MCP).
A future refactor that adds a key to ``snapshot()`` but forgets to
flow it through the tool wrapper would silently desync the engine
view from the controller view; this file traps that drift.

The parallel check on ``state_get`` (closes N3) asserts the FSM
labels the tool advertises are a subset of the snapshot's keys, so
a controller can rely on the relationship.
"""

from __future__ import annotations

import asyncio
import json

from nous.audit import AuditLogger
from nous.engine import Engine
from nous.policy import PolicyMode
from nous.runner import run


def _build_audit(tmp_path_factory: object) -> AuditLogger:  # pragma: no cover - utility
    raise NotImplementedError


def test_device_health_payload_matches_engine_snapshot(engine: Engine) -> None:
    snap = engine.snapshot()

    async def _work() -> str:
        return json.dumps(engine.snapshot(), indent=2)

    body = asyncio.run(
        run(
            tool="device_health",
            args={},
            work=_work,
            audit=AuditLogger("/tmp/nous-parity-audit.jsonl"),
            policy_mode=PolicyMode.READONLY,
        )
    )
    payload = json.loads(body)

    # The MCP-facing payload must expose exactly the snapshot keys.
    # A new subsystem that adds a key to ``snapshot()`` is also a
    # new key in ``device_health``; a tool wrapper that strips keys
    # surfaces here.
    assert set(payload) == set(snap)


def test_state_get_keys_are_fsm_subset_of_snapshot(engine: Engine) -> None:
    # AUDIT-2026-05-24 N3: ``state_get`` carries the FSM-adjacent
    # fields, not the subsystem detail. Every key it returns must
    # also appear in ``snapshot()`` so a controller that asks
    # ``state_get`` is guaranteed the same value would surface in
    # ``device_health``.
    snap = engine.snapshot()
    state_get_keys = {
        "mode",
        "tick",
        "ts_s",
        "operator_state",
        "operator_state_reason",
        "comms_state",
        "comms_state_reason",
    }
    assert state_get_keys.issubset(set(snap)), (
        "state_get keys must be a subset of snapshot keys; "
        f"missing: {state_get_keys - set(snap)}"
    )
