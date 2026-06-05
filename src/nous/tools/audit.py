"""Audit-trail tools (ADR 0021).

The audit-sink reads (T0: summary, hash-chain verify, daily-anchor verify) and
the in-place sink recovery (T2: resync), extracted from ``server.py``. Handler
bodies and docstrings are byte-faithful to the inline definitions they replace,
so the registered tool surface does not change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

from ..audit import verify_chain

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the audit-trail tools on ``mcp``."""

    @mcp.tool()
    async def audit_summary(ctx: Context | None = None) -> str:
        """Read-only view of the audit handler's state.

        Surfaces the full audit-handler picture: file path, degraded
        flag and reason, cumulative ``fsync_failures``, cumulative
        ``writes_total``, ``last_write_ts_s`` (unix timestamp of the
        most recent durable write; ``None`` if no writes yet), and
        the ``also_stderr`` echo flag. A controller comparing
        ``writes_total`` against the tick cadence can detect a
        silently-dropping handler that ``device_info.audit.degraded``
        would not catch (the handler accepted the write but the
        underlying fsync failed; the counter contract gates the
        increment on durability per PR #60 review).

        Closes the registration gap in ``policy.py`` (``audit_summary``
        was classified T0 but never wired). Tier T0 (read-only): the
        ``AuditLogger.summary()`` method itself does not mutate
        handler state. The surrounding ``_wrap`` audited-runner
        call still writes one audit record (as every tool call
        does, per ADR 0001); the snapshot returned here is captured
        before that wrap record lands, so the response shows the
        pre-call state. Successive ``audit_summary`` calls therefore
        increase ``writes_total`` by one per call in the live
        audit log, even though each response is "one behind."
        """

        async def _work() -> str:
            return json.dumps(app.audit.summary(), indent=2)

        return await wrap("audit_summary", {}, ctx, _work)

    @mcp.tool()
    async def audit_resync(ctx: Context | None = None) -> str:
        """Re-open the audit sink in place (closes AUDIT-2026-05-23 N2).

        Use after an operator has remediated the underlying cause of a
        degraded audit sink (typically: filesystem permissions or
        mount, ``ReadWritePaths=`` drift on the systemd unit, the
        audit file being moved out from under the handler). The tool
        attempts to re-open ``device_info.audit.path``; on success the
        ``audit.degraded`` flag clears without a service restart.

        Tier T2 (stateful): mutates the in-process audit handler.
        ``fsync_failures`` is the cumulative counter and is not
        reset, so the operator can still see the loss window.
        """

        async def _work() -> str:
            return json.dumps(app.audit.resync(), indent=2)

        return await wrap("audit_resync", {}, ctx, _work)

    @mcp.tool()
    async def audit_verify(ctx: Context | None = None) -> str:
        """Verify the audit hash chain on disk (BL-016, ADR 0025).

        Walks ``device_info.audit.path`` and recomputes the chain: each
        line commits to its predecessor through ``prev_hash`` /
        ``entry_hash``, so a mutated record or a mid-stream deletion
        breaks a link the walk reports at ``first_break_line``. The
        response carries ``ok`` (linkage intact), ``from_genesis`` (the
        log roots at genesis; false for a post-rotation continuation
        segment, which is still ``ok``), the line counts (``lines`` /
        ``chained`` / ``legacy``), the verified ``head``, and the break
        ``reason`` when ``ok`` is false. Pre-chain lines are counted as
        ``legacy`` and skipped, so a log that straddles the upgrade still
        verifies.

        Tier T0 (read-only): the verifier only reads the file. It does
        not detect truncation, which the BL-031 daily anchor closes.
        """

        async def _work() -> str:
            return json.dumps(verify_chain(app.audit.path), indent=2)

        return await wrap("audit_verify", {}, ctx, _work)

    @mcp.tool()
    async def audit_anchor_verify(ctx: Context | None = None) -> str:
        """Cross-check the daily audit anchors against the chain (BL-031, ADR 0026).

        The BL-016 hash chain (``audit_verify``) catches mutation and
        mid-stream deletion but not tail truncation: dropping the most
        recent records leaves a shorter, still-consistent chain. The daily
        anchor closes that gap by pinning the chain head once per UTC day in
        a separate append-only file (``device_info.audit.anchor_path``). This
        tool reconstructs the audit chain across logrotate segments and
        confirms every anchored head is still present; a missing anchored
        head means the trail was truncated below the anchor, reported in
        ``reason`` and ``first_break``. ``unverifiable`` counts anchors that
        predate the oldest retained segment (rotated out, not a break).

        Tier T0 (read-only): reads the audit and anchor files; mutates
        nothing.
        """

        async def _work() -> str:
            from ..audit_anchor import verify_anchors

            return json.dumps(verify_anchors(app.audit.path, app.anchor.path), indent=2)

        return await wrap("audit_anchor_verify", {}, ctx, _work)
