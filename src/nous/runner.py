"""Audited execution wrapper for MCP tool calls.

Every tool registered in ``nous.server`` runs through ``run()``. The wrapper:

1. classifies the tool into a tier (`nous.policy.classify`),
2. admits or refuses the call under the configured mode (`nous.policy.decide`),
3. executes the supplied ``work`` coroutine, catching every exception and
   reducing it to its class name in the returned body (the full detail goes
   to stderr, never to the caller; ADR 0055),
4. truncates the body to the configured output budget,
5. appends one audit line (the body's SHA-256, never the body itself).

The runner returns a single bounded string suitable for an MCP tool response.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .audit import AuditLogger, AuditRecord, redact
from .policy import PolicyMode, classify, decide

__all__ = ["run"]

Work = Callable[[], Awaitable[str]]


def _truncate(body: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(body) <= limit:
        return body
    return body[:limit] + f"\n...<truncated {len(body) - limit} bytes>"


async def run(
    *,
    tool: str,
    args: Mapping[str, Any],
    work: Work,
    audit: AuditLogger,
    policy_mode: PolicyMode,
    deny: str = "",
    allow: str = "",
    probe: str = "",
    max_output: int = 65536,
    request_id: str = "",
    client_id: str = "",
) -> str:
    """Run ``work`` under audit, returning the (possibly truncated) body."""
    tier, _why = classify(tool, args)
    decision = decide(tier, policy_mode, deny=deny, allow=allow, probe=probe or tool)
    redacted = redact(args)

    if not decision.allowed:
        body = f"[DENIED tier {int(decision.tier)} ({decision.tier.name}): {decision.reason}]"
        # Stamp ``exit_code=1`` on the denial record so an operator can
        # count denials per tier per day without parsing the body string.
        # Closes AUDIT-2026-05-20 M1.
        audit.write(
            AuditRecord.from_output(
                tool=tool,
                tier=int(decision.tier),
                args=redacted,
                output=body,
                denied=True,
                decision_reason=decision.reason,
                policy_mode=policy_mode.value,
                exit_code=1,
                request_id=request_id,
                client_id=client_id,
            )
        )
        return body

    error = False
    try:
        body = await work()
    except Exception as exc:  # noqa: BLE001
        # The body carries only the class name: a backend error message can
        # embed a data-source URL with credentials, and this body is returned
        # to the caller (ADR 0055). The full detail goes to stderr for an
        # operator with host access, mirroring the server's DB-init handler.
        body = f"[error {exc.__class__.__name__}]"
        error = True
        # Escape embedded newlines so a crafted message cannot forge extra
        # journal lines, and flush so the entry lands as one reliable line.
        detail = f"tool {tool} failed: {exc.__class__.__name__}: {exc}"
        detail = detail.replace("\n", "\\n").replace("\r", "\\r")
        with contextlib.suppress(Exception):
            sys.stderr.write(detail + "\n")
            sys.stderr.flush()

    body = _truncate(body, max_output)
    # Stamp ``exit_code=1`` on a caught worker exception so a consumer can tell
    # it apart from a normal return on the typed field, not the body prefix
    # (ADR 0048, closes AUDIT-2026-06-14 RUN-1). The contract is two-valued:
    # ``None`` is a normal return, ``1`` is any abnormal outcome, and the
    # ``denied`` flag separates a policy refusal (denied) from a caught error.
    audit.write(
        AuditRecord.from_output(
            tool=tool,
            tier=int(decision.tier),
            args=redacted,
            output=body,
            decision_reason=decision.reason,
            policy_mode=policy_mode.value,
            exit_code=1 if error else None,
            request_id=request_id,
            client_id=client_id,
        )
    )
    return body
