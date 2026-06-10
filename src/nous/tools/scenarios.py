"""Scenario and configuration tools (ADR 0021, ADR 0040).

Profile hot-reload (T2 configuration), the scenario runner in both its
one-shot and stateful-session forms (T2 load), the session control verbs
(T0 status read, T1 pause / resume / reset), the ad-hoc injector (T2), and
deterministic tick stepping (T1 ``tick_advance``). The session verbs and
``tick_advance`` were classified in ``policy.py`` from L0 (ADR 0007) and
register here once the stateful runner exists (ADR 0040).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import anyio.lowlevel
from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..scenarios.session import ScenarioSession
    from ..server import Nous, WrapFn

# Upper bound on ticks one tick_advance call may run, and how often the
# loop yields to the event loop. A tick costs about a millisecond on the
# reference profile (the Monte Carlo capability refresh dominates; BL-073),
# so an unyielding 600-tick run measures ~0.6 s -- longer than the 500 ms
# inter-tick budget at the default 2 Hz. The periodic checkpoint keeps the
# server and the live tick loop responsive during the advance; 600 ticks
# still covers five minutes of simulated time per call at 2 Hz.
_TICK_ADVANCE_MAX = 600
_TICK_ADVANCE_YIELD_EVERY = 50


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the scenario and configuration tools on ``mcp``."""

    def _control_verb(op: Callable[[ScenarioSession], tuple[bool, str]]) -> str:
        """Shared pause/resume body: one place owns the control-verb contract."""
        session = app.scenario_session
        if session is None:
            return json.dumps({"ok": False, "error": "no scenario session"})
        ok, reason = op(session)
        out: dict[str, Any] = {"ok": ok, "state": session.state.value}
        if not ok:
            out["error"] = reason
        return json.dumps(out)

    @mcp.tool()
    async def profile_reload(
        name: str = "", ctx: Context | None = None
    ) -> str:
        """Hot-reload the hardware profile from disk.

        ``name`` defaults to the currently-active profile; pass a
        different name to switch profiles entirely. Subsystems and
        estimators are rebuilt; FSM mode and tick counter are
        preserved. Returns a summary the controller can audit.
        """

        async def _work() -> str:
            summary = app.engine.reload_profile(name=name or None)
            return json.dumps(summary)

        return await wrap("profile_reload", {"name": name}, ctx, _work)

    @mcp.tool()
    async def scenario_load(
        path: str, mode: str = "run", ctx: Context | None = None
    ) -> str:
        """Load a scenario YAML and execute it against the engine (T2).

        ``mode="run"`` (the default) drives the engine through the
        scenario's tick budget inside this call and returns the structured
        run report -- a long scenario blocks the tool call. ``mode="session"``
        starts the scenario as a stateful session riding the live tick loop
        (ADR 0040) and returns immediately with the session's initial
        status; progress is read with ``scenario_status``, controlled with
        ``scenario_pause`` / ``scenario_resume`` / ``scenario_reset``, and
        fast-forwarded with ``tick_advance``.

        Either mode refuses while a session is running or paused
        (``scenario_reset`` clears it), so two timelines never interleave;
        a finished session is cleared by the next load.

        If the scenario names a profile that does not match the
        currently-mounted one, the engine hot-reloads to the requested
        profile (BL-039) before running so the physics matches the
        declared scenario environment.
        """

        async def _work() -> str:
            from ..scenarios import load_scenario_file, run_scenario, start_session

            if mode not in ("run", "session"):
                return json.dumps(
                    {
                        "ok": False,
                        "error": f"unknown mode {mode!r}; expected 'run' or 'session'",
                    }
                )
            active = app.scenario_session
            if active is not None:
                if active.active:
                    return json.dumps(
                        {
                            "ok": False,
                            "error": (
                                "a scenario session is already active; "
                                "scenario_reset clears it"
                            ),
                            "session": active.status(include_records=False),
                        }
                    )
                # A finished session does not block, but it must not linger:
                # scenario_status would otherwise keep reporting it against
                # an engine the new scenario has moved on.
                active.close()
                app.scenario_session = None
            scenario = load_scenario_file(path)
            reloaded_from = ""
            if scenario.profile and scenario.profile != app.engine.settings.profile:
                reloaded_from = app.engine.settings.profile
                app.engine.reload_profile(name=scenario.profile)
            if mode == "session":
                session = start_session(app.engine, scenario)
                app.scenario_session = session
                payload: dict[str, Any] = {
                    "ok": True,
                    "mode": "session",
                    "session": session.status(),
                }
                if reloaded_from:
                    payload["profile_reloaded_from"] = reloaded_from
                return json.dumps(payload)
            report = dict(run_scenario(app.engine, scenario))
            if reloaded_from:
                report["profile_reloaded_from"] = reloaded_from
            return json.dumps(report)

        return await wrap(
            "scenario_load", {"path": path, "mode": mode}, ctx, _work
        )

    @mcp.tool()
    async def scenario_status(ctx: Context | None = None) -> str:
        """Progress of the stateful scenario session, if any (T0, ADR 0040).

        Returns ``{"active": false}`` when no session exists. Otherwise the
        payload carries the session state (``running`` / ``paused`` /
        ``done``), the scenario clock (``ticks_run``, ``elapsed_min``
        against ``tick_budget``), step counters, the next pending step, and
        the per-step records fired so far. Once the session is done the
        payload also carries the ``snapshot`` captured when the budget
        completed (not a later live read; the engine keeps ticking), making
        it content-equivalent to the ``mode="run"`` report.
        """

        async def _work() -> str:
            session = app.scenario_session
            if session is None:
                return json.dumps({"active": False})
            payload: dict[str, Any] = {"active": session.active, **session.status()}
            if session.final_snapshot is not None:
                payload["snapshot"] = session.final_snapshot
            return json.dumps(payload)

        return await wrap("scenario_status", {}, ctx, _work)

    @mcp.tool()
    async def scenario_pause(ctx: Context | None = None) -> str:
        """Freeze the scenario session's clock (T1, reversible; ADR 0040).

        The device keeps ticking; the session stops consuming ticks, so no
        further steps fire and the budget stops counting down until
        ``scenario_resume``. Pausing an already-paused session is a no-op;
        a done or missing session is refused.
        """

        async def _work() -> str:
            return _control_verb(lambda s: s.pause())

        return await wrap("scenario_pause", {}, ctx, _work)

    @mcp.tool()
    async def scenario_resume(ctx: Context | None = None) -> str:
        """Unfreeze a paused scenario session (T1, reversible; ADR 0040).

        The session resumes consuming ticks exactly where its scenario
        clock stopped. Resuming a running session is a no-op; a done or
        missing session is refused.
        """

        async def _work() -> str:
            return _control_verb(lambda s: s.resume())

        return await wrap("scenario_resume", {}, ctx, _work)

    @mcp.tool()
    async def scenario_reset(ctx: Context | None = None) -> str:
        """Detach and clear the scenario session (T1; ADR 0040).

        Clears the *session* -- the timeline, its clock, and its pending
        steps -- so a new scenario can load. Injections the session already
        applied are engine state and persist; reversing them is the
        controller's call (that asymmetry is why ``scenario_load`` is T2
        while reset is T1). Resetting when no session exists is a no-op.
        """

        async def _work() -> str:
            session = app.scenario_session
            if session is None:
                return json.dumps({"ok": True, "cleared": False})
            session.close()
            app.scenario_session = None
            return json.dumps(
                {
                    "ok": True,
                    "cleared": True,
                    "state_at_reset": session.state.value,
                    "name": session.scenario.name,
                    "ticks_run": session.ticks_run,
                    "steps_fired": session.steps_fired,
                }
            )

        return await wrap("scenario_reset", {}, ctx, _work)

    @mcp.tool()
    async def tick_advance(n: int = 1, ctx: Context | None = None) -> str:
        """Advance simulated time by ``n`` engine ticks, synchronously (T1).

        Deterministic stepping for scenario debugging and fast-forward:
        each tick advances every subsystem, estimator, and any active
        scenario session by ``dt = 1 / tick_hz`` of simulated time. Safe
        alongside the live tick loop -- tools and the loop share one event
        loop and a tick is synchronous, so steps never interleave; the
        wall-clock cadence simply gains ``n`` extra ticks, and the loop may
        add its own ticks while a long advance yields (ADR 0040). ``n`` is
        bounded to [1, 600] to keep one call from monopolising the server;
        chain calls for longer jumps.
        """

        async def _work() -> str:
            count = int(n)
            if count < 1 or count > _TICK_ADVANCE_MAX:
                return json.dumps(
                    {
                        "ok": False,
                        "error": f"n must be in [1, {_TICK_ADVANCE_MAX}]",
                        "tick": app.engine.state.tick,
                    }
                )
            for done in range(1, count + 1):
                app.engine.tick()
                if done % _TICK_ADVANCE_YIELD_EVERY == 0:
                    await anyio.lowlevel.checkpoint()
            return json.dumps(
                {
                    "ok": True,
                    "ticks_advanced": count,
                    "tick": app.engine.state.tick,
                    "ts_s": round(app.engine.state.ts_s, 3),
                    "mode": app.engine.state.mode.value,
                }
            )

        return await wrap("tick_advance", {"n": n}, ctx, _work)

    @mcp.tool()
    async def scenario_inject(
        action: str,
        args: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Fire a single scenario injector against the live engine.

        Useful for ad-hoc what-ifs without the overhead of writing a
        YAML scenario. ``action`` matches the names in
        :mod:`nous.scenarios.injectors`. An ad-hoc injection is audited
        like any tool call but is outside any active scenario session's
        timeline: it does not appear in the session's records or counters.
        """

        async def _work() -> str:
            from ..scenarios.injectors import apply_injection

            outcome = apply_injection(app.engine, action, args or {})
            return json.dumps(outcome)

        return await wrap(
            "scenario_inject",
            {"action": action, "args": dict(args or {})},
            ctx,
            _work,
        )
