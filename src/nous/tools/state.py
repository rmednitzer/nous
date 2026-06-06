"""FSM-state tools (ADR 0021, ADR 0031, ADR 0032).

The current-mode reads (state_get, state_history) plus the posture-control
writes: state_transition (T2, ADR 0031) drives the reversible mission-posture
transitions, and state_force_fault / state_force_shutdown (T3, ADR 0032) are
the irreversible terminal-control tools that state_transition deliberately
refuses. state_get / state_history were extracted byte-faithfully from
``server.py``; the write tools wrap ``Engine.request_transition``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

from ..state.machine import is_terminal

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

    @mcp.tool()
    async def state_transition(trigger: str, ctx: Context | None = None) -> str:
        """Drive the mission-posture FSM through one explicit trigger (ADR 0031).

        Fires ``trigger`` against the current FSM mode: ``ready`` leaves BOOT
        for IDLE, then ``mission`` / ``relay`` / ``monitoring`` / ``c2`` go
        operational, and ``safe`` is the recoverable failsafe hold. Entries
        into an operational mode are safety-gated (SC-2 thermal headroom, SC-8
        power reserve) against the engine's live context. The tool takes no
        caller-supplied safety context on purpose, so a controller cannot
        spoof the gate inputs: an operational entry always judges the real
        thermal and state-of-charge values.

        The terminal triggers ``fault`` and ``shutdown`` are refused here.
        They reach the reset-only FAULT / SHUTDOWN modes, which are the
        province of the irreversible (T3) ``state_force_fault`` /
        ``state_force_shutdown`` tools, not this reversible (T2) control
        surface; refusing them keeps the T2 / T3 split intact under guarded
        mode (where ``state_transition`` may be the only allowlisted write).

        Returns a JSON object ``{"ok": bool, "mode": str, "reason": str}``.
        ``ok`` is ``false`` for an unknown table edge, a refused terminal
        trigger, or a guard refusal, so the controller reads one observable
        outcome instead of catching an exception. Tier T2 (stateful): a
        successful call changes the device posture and is audited.
        """

        async def _work() -> str:
            destination = app.engine.fsm.would(trigger)
            if destination is not None and is_terminal(destination):
                return json.dumps(
                    {
                        "ok": False,
                        "mode": app.engine.state.mode.value,
                        "reason": (
                            f"{trigger!r} reaches terminal {destination.value!r}; "
                            "use the irreversible state_force_* tool"
                        ),
                    }
                )
            ok, mode, reason = app.engine.request_transition(trigger)
            return json.dumps({"ok": ok, "mode": mode.value, "reason": reason})

        return await wrap("state_transition", {"trigger": trigger}, ctx, _work)

    @mcp.tool()
    async def state_force_fault(ctx: Context | None = None) -> str:
        """Force the device into the terminal FAULT posture (T3, ADR 0032).

        Fires the FSM ``fault`` trigger, which ADR 0030 makes reachable in one
        step from every powered mode. FAULT is terminal: it leaves only via a
        ``reset`` (which reboots through STOWED), so this is the irreversible
        (T3) counterpart to the reversible ``state_transition`` tool, which
        refuses ``fault`` for exactly this reason. Recovery is a separate,
        deliberate act: ``state_transition`` with ``reset`` then ``boot``.

        Returns ``{"ok": bool, "mode": str, "reason": str}``; ``ok`` is
        ``false`` only where the table offers no ``fault`` edge (the device is
        already terminal, or STOWED). Tier T3 (irreversible): refused by
        ``guarded`` and ``readonly`` policy modes unless explicitly allowed.
        """

        async def _work() -> str:
            ok, mode, reason = app.engine.request_transition("fault")
            return json.dumps({"ok": ok, "mode": mode.value, "reason": reason})

        return await wrap("state_force_fault", {}, ctx, _work)

    @mcp.tool()
    async def state_force_shutdown(ctx: Context | None = None) -> str:
        """Force the device into the terminal SHUTDOWN posture (T3, ADR 0032).

        Fires the FSM ``shutdown`` trigger. SHUTDOWN is terminal (``reset``
        only), so like ``state_force_fault`` this is the irreversible (T3) path
        that ``state_transition`` refuses. This drives the *modelled* shutdown
        posture; it does not stop the simulator process (that is the engine
        lifecycle's ``stop``). Recovery is ``state_transition`` with ``reset``
        then ``boot``.

        Returns ``{"ok": bool, "mode": str, "reason": str}``; ``ok`` is
        ``false`` from a mode with no ``shutdown`` edge (STOWED, FAULT, or
        already SHUTDOWN). Tier T3 (irreversible): refused by ``guarded`` and
        ``readonly`` policy modes unless explicitly allowed.
        """

        async def _work() -> str:
            ok, mode, reason = app.engine.request_transition("shutdown")
            return json.dumps({"ok": ok, "mode": mode.value, "reason": reason})

        return await wrap("state_force_shutdown", {}, ctx, _work)
