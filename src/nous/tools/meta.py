"""Device telemetry tools (ADR 0021).

The read-only device-identity and engine-snapshot reads (T0), extracted from
``server.py``. The audited-runner ``wrap`` and the
:class:`~nous.server.Nous` app are threaded in by :func:`register`; handler
bodies and docstrings are byte-faithful to the inline definitions they
replace, so the registered tool surface does not change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

from .. import __version__

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the device telemetry tools on ``mcp``."""
    cfg = app.settings

    @mcp.tool()
    async def device_info(ctx: Context | None = None) -> str:
        """Report nous version, profile, transport, policy mode, audit and anchor paths."""

        async def _work() -> str:
            info = {
                "name": "nous",
                "version": __version__,
                "profile": cfg.profile,
                "transport": cfg.transport,
                "policy": cfg.policy,
                "tick_hz": cfg.tick_hz,
                "audit": {
                    "path": app.audit.path,
                    "degraded": app.audit.degraded,
                    "anchor_path": app.anchor.path,
                    "anchor_degraded": app.anchor.degraded,
                },
            }
            return json.dumps(info, indent=2)

        return await wrap("device_info", {}, ctx, _work)

    @mcp.tool()
    async def device_health(ctx: Context | None = None) -> str:
        """Engine snapshot: tick, ts_s, mode, operator/comms state."""

        async def _work() -> str:
            return json.dumps(app.engine.snapshot(), indent=2)

        return await wrap("device_health", {}, ctx, _work)
