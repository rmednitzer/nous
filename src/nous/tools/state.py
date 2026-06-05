"""FSM-state tools (ADR 0021).

The current-mode read (state_get) and the transition history (state_history),
extracted from ``server.py``. Byte-faithful to the inline definitions they
replace, so the registered tool surface does not change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the FSM-state tools on ``mcp``."""

    @mcp.tool()
    async def state_get(ctx: Context | None = None) -> str:
        """Current FSM mode plus the labels a controller queries together.

        Closes AUDIT-2026-05-24 N3 (minimal payload). The shape stays
        narrow on purpose (FSM-adjacent fields only); a controller that
        needs subsystem-level detail uses ``device_health`` instead.
        """

        async def _work() -> str:
            state = app.engine.state
            return json.dumps(
                {
                    "mode": state.mode.value,
                    "tick": state.tick,
                    "ts_s": state.ts_s,
                    "operator_state": state.operator_state.value,
                    "operator_state_reason": state.operator_state_reason,
                    "comms_state": state.comms_state.value,
                    "comms_state_reason": state.comms_state_reason,
                }
            )

        return await wrap("state_get", {}, ctx, _work)

    @mcp.tool()
    async def state_history(limit: int = 16, ctx: Context | None = None) -> str:
        """Recent FSM transitions (oldest first; up to ``limit`` rows).

        Prefers the SQLite ``state_transitions`` table when available so
        history survives a restart; falls back to the in-memory FSM
        history when the DB is unreachable (kept consistent with the
        audit logger's "best effort" posture).
        """

        async def _work() -> str:
            n = max(1, min(limit, 256))
            db_rows = app.transition_log.tail(n)
            if db_rows:
                rows = [
                    {
                        "from": r.from_mode,
                        "trigger": r.trigger,
                        "to": r.to_mode,
                        "reason": r.reason,
                        "ts": r.ts.isoformat(),
                        "source": "sqlite",
                    }
                    for r in db_rows
                ]
            else:
                hist = app.engine.fsm.history()[-n:]
                rows = [
                    {
                        "from": f.value,
                        "trigger": t,
                        "to": n2.value,
                        "reason": "",
                        "ts": "",
                        "source": "memory",
                    }
                    for (f, t, n2) in hist
                ]
            return json.dumps(rows, indent=2)

        return await wrap("state_history", {"limit": limit}, ctx, _work)
