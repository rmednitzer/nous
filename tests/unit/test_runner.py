"""Audited runner contract: admission, denial, exception mapping, truncation.

Closes ``AUDIT.md`` H1 for the runner half. The existing
``test_policy.py`` covers the classifier and the admission matrix in
isolation; this file exercises the full execution path through
``runner.run``: the four tiers, the three policy modes, the
denial-path audit record (now with ``exit_code=1`` per the M1 fix),
exception-to-body mapping, the truncation budget, the redaction
allowlist wired through to the audit log, and the request / client
identifier plumbing.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from nous.audit import AuditLogger
from nous.policy import PolicyMode
from nous.runner import run


@pytest.fixture
def audit(tmp_path: Path) -> AuditLogger:
    return AuditLogger(tmp_path / "audit.jsonl")


def _last_record(logger: AuditLogger) -> dict[str, object]:
    logger.flush()
    raw = Path(logger.path).read_text(encoding="utf-8").strip().splitlines()[-1]
    obj: dict[str, object] = json.loads(raw)
    return obj


async def _ok_work() -> str:
    return "ok"


async def _raising_work() -> str:
    raise RuntimeError("boom")


async def _long_work() -> str:
    return "x" * 200_000


def test_t0_call_under_readonly_is_admitted(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="device_info",
            args={},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.READONLY,
        )
    )
    assert body == "ok"
    record = _last_record(audit)
    assert record["tool"] == "device_info"
    assert record["tier"] == 0
    assert record["denied"] is False
    assert record.get("exit_code") is None


def test_t2_call_under_readonly_denied_with_exit_code_one(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="state_transition",
            args={"to": "mission"},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.READONLY,
        )
    )
    assert body.startswith("[DENIED tier 2 (STATEFUL):")
    record = _last_record(audit)
    assert record["denied"] is True
    assert record["exit_code"] == 1
    assert record["tier"] == 2


def test_t2_call_under_guarded_without_allow_denied(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="scenario_load",
            args={"path": "x.yaml"},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.GUARDED,
        )
    )
    assert "DENIED" in body
    record = _last_record(audit)
    assert record["denied"] is True
    assert record["exit_code"] == 1


def test_t2_call_under_guarded_with_allow_regex_admitted(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="scenario_load",
            args={"path": "x.yaml"},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.GUARDED,
            allow=r"^scenario_",
        )
    )
    assert body == "ok"
    record = _last_record(audit)
    assert record["denied"] is False


def test_t3_call_under_open_mode_admitted(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="db_reset",
            args={},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.OPEN,
        )
    )
    assert body == "ok"
    record = _last_record(audit)
    assert record["tier"] == 3
    assert record["denied"] is False


def test_exception_in_work_maps_to_error_body(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="device_info",
            args={},
            work=_raising_work,
            audit=audit,
            policy_mode=PolicyMode.OPEN,
        )
    )
    assert body == "[error RuntimeError: boom]"
    record = _last_record(audit)
    assert record["denied"] is False
    assert record.get("exit_code") is None


def test_body_truncated_to_max_output(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="device_info",
            args={},
            work=_long_work,
            audit=audit,
            policy_mode=PolicyMode.OPEN,
            max_output=128,
        )
    )
    assert body.startswith("x" * 128)
    assert "<truncated " in body
    record = _last_record(audit)
    assert "output_sha256" in record
    assert record["output_len"] == len(body.encode("utf-8"))


def test_redaction_runs_before_audit(audit: AuditLogger) -> None:
    asyncio.run(
        run(
            tool="device_info",
            args={"Authorization": "Bearer secret"},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.OPEN,
        )
    )
    record = _last_record(audit)
    args = record["args"]
    assert isinstance(args, dict)
    assert args["Authorization"] == "<REDACTED>"


def test_deny_regex_refuses_even_under_open_mode(audit: AuditLogger) -> None:
    body = asyncio.run(
        run(
            tool="device_info",
            args={},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.OPEN,
            deny=r"device_info",
        )
    )
    assert "DENIED" in body
    record = _last_record(audit)
    assert record["denied"] is True
    assert "NOUS_POLICY_DENY" in str(record["decision_reason"])


def test_request_and_client_id_flow_through(audit: AuditLogger) -> None:
    asyncio.run(
        run(
            tool="device_info",
            args={},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.OPEN,
            request_id="req-1",
            client_id="client-1",
        )
    )
    record = _last_record(audit)
    assert record["request_id"] == "req-1"
    assert record["client_id"] == "client-1"


def test_unknown_tool_defaults_to_stateful_under_additive_surface(
    audit: AuditLogger,
) -> None:
    body = asyncio.run(
        run(
            tool="never_seen_before",
            args={},
            work=_ok_work,
            audit=audit,
            policy_mode=PolicyMode.READONLY,
        )
    )
    assert body.startswith("[DENIED")
    record = _last_record(audit)
    assert record["tier"] == 2
    assert record["denied"] is True
