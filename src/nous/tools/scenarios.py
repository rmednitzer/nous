"""Scenario and configuration tools (ADR 0021).

Profile hot-reload (T2 configuration) plus the scenario runner and the ad-hoc
injector (T2), extracted from ``server.py``. Handler bodies and docstrings are
byte-faithful to the inline definitions they replace, so the registered tool
surface does not change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the scenario and configuration tools on ``mcp``."""

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
    async def scenario_load(path: str, ctx: Context | None = None) -> str:
        """Load and run a scenario YAML against the engine.

        Returns the structured run report (steps fired, snapshot after
        the last tick). The runner advances the engine through the
        scenario's tick budget, so a long scenario blocks the tool
        call -- a future enhancement (BL-014) can switch to background
        execution if the controller needs to interleave reads.

        If the scenario names a profile that does not match the
        currently-mounted one, the engine hot-reloads to the requested
        profile (BL-039) before running so the report's physics matches
        the declared scenario environment.
        """

        async def _work() -> str:
            from ..scenarios import load_scenario_file, run_scenario

            scenario = load_scenario_file(path)
            reloaded_from = ""
            if scenario.profile and scenario.profile != app.engine.settings.profile:
                reloaded_from = app.engine.settings.profile
                app.engine.reload_profile(name=scenario.profile)
            report = dict(run_scenario(app.engine, scenario))
            if reloaded_from:
                report["profile_reloaded_from"] = reloaded_from
            return json.dumps(report)

        return await wrap("scenario_load", {"path": path}, ctx, _work)

    @mcp.tool()
    async def scenario_inject(
        action: str,
        args: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Fire a single scenario injector against the live engine.

        Useful for ad-hoc what-ifs without the overhead of writing a
        YAML scenario. ``action`` matches the names in
        :mod:`nous.scenarios.injectors`.
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
