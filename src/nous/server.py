"""FastMCP server: representative tools wired through the audited runner.

Every tool runs through :func:`nous.runner.run`. The handler returns a
single bounded string. The tools registered here are the *representative*
v0.1 surface; full subsystem coverage lands in L1 (see ``docs/backlog.md``).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from . import __version__
from .audit import AuditLogger
from .config import Settings, get_settings
from .engine import Engine
from .policy import PolicyMode
from .runner import run as audited_run

__all__ = ["Nous", "build_server"]


Work = Callable[[], Awaitable[str]]


def _ctx_ids(ctx: Context | None) -> tuple[str, str]:
    if ctx is None:
        return "", ""
    request_id = ""
    client_id = ""
    with contextlib.suppress(Exception):
        request_id = str(getattr(ctx, "request_id", "") or "")
    with contextlib.suppress(Exception):
        client_id = str(getattr(ctx, "client_id", "") or "")
    return request_id, client_id


class Nous:
    """Server-wide state: settings, audit sink, engine."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditLogger(str(settings.resolved_audit_path()))
        self.engine = Engine(settings=settings)
        self.engine.start()

    @property
    def policy_mode(self) -> PolicyMode:
        return PolicyMode(self.settings.policy)


def build_server(settings: Settings | None = None) -> FastMCP:
    """Construct the FastMCP server with every tool registered."""
    cfg = settings or get_settings()
    app = Nous(cfg)

    host, _, port_str = cfg.http_bind.partition(":")
    try:
        port = int(port_str) if port_str else 8088
    except ValueError:
        port = 8088

    fastmcp_kwargs: dict[str, Any] = {
        "instructions": _INSTRUCTIONS,
        "host": host or "127.0.0.1",
        "port": port,
        "stateless_http": True,
        "json_response": True,
    }
    if cfg.transport == "http" and cfg.oauth_enabled:
        from .auth import build_auth_settings, make_oauth_provider

        fastmcp_kwargs["auth"] = build_auth_settings(cfg.oauth_issuer)
        fastmcp_kwargs["auth_server_provider"] = make_oauth_provider(cfg)

    mcp = FastMCP("nous", **fastmcp_kwargs)

    async def _wrap(
        tool: str,
        args: dict[str, Any],
        ctx: Context | None,
        work: Work,
    ) -> str:
        request_id, client_id = _ctx_ids(ctx)
        return await audited_run(
            tool=tool,
            args=args,
            work=work,
            audit=app.audit,
            policy_mode=app.policy_mode,
            deny=cfg.policy_deny,
            allow=cfg.policy_allow,
            probe=tool,
            max_output=cfg.max_output,
            request_id=request_id,
            client_id=client_id,
        )

    @mcp.tool()
    async def device_info(ctx: Context | None = None) -> str:
        """Report nous version, profile, transport, policy mode, audit path."""

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
                },
            }
            return json.dumps(info, indent=2)

        return await _wrap("device_info", {}, ctx, _work)

    @mcp.tool()
    async def device_health(ctx: Context | None = None) -> str:
        """Engine snapshot: tick, ts_s, mode, operator/comms state."""

        async def _work() -> str:
            return json.dumps(app.engine.snapshot(), indent=2)

        return await _wrap("device_health", {}, ctx, _work)

    @mcp.tool()
    async def state_get(ctx: Context | None = None) -> str:
        """Current FSM mode."""

        async def _work() -> str:
            return json.dumps(
                {"mode": app.engine.state.mode.value, "tick": app.engine.state.tick}
            )

        return await _wrap("state_get", {}, ctx, _work)

    @mcp.tool()
    async def state_history(limit: int = 16, ctx: Context | None = None) -> str:
        """Recent FSM transitions (oldest first; up to ``limit`` rows)."""

        async def _work() -> str:
            hist = app.engine.fsm.history()[-max(1, min(limit, 256)) :]
            rows = [
                {"from": f.value, "trigger": t, "to": n.value} for (f, t, n) in hist
            ]
            return json.dumps(rows, indent=2)

        return await _wrap(
            "state_history", {"limit": limit}, ctx, _work
        )

    @mcp.tool()
    async def power_status(ctx: Context | None = None) -> str:
        """Battery state-of-charge, draw, projected endurance (placeholder)."""

        async def _work() -> str:
            return json.dumps(
                {
                    "soc_pct": None,
                    "draw_w": None,
                    "endurance_min_p50": None,
                    "note": "power subsystem ships as a typed stub in v0.1",
                }
            )

        return await _wrap("power_status", {}, ctx, _work)

    @mcp.tool()
    async def apu_status(ctx: Context | None = None) -> str:
        """Auxiliary-power-unit state (solar, fuel cell)."""

        async def _work() -> str:
            return json.dumps(
                {
                    "solar_w": None,
                    "fuelcell_w": None,
                    "fuelcell_fuel_pct": None,
                    "note": "APU subsystem ships as a typed stub in v0.1",
                }
            )

        return await _wrap("apu_status", {}, ctx, _work)

    @mcp.tool()
    async def comms_state(ctx: Context | None = None) -> str:
        """Comms-stack summary (per ADR-0006)."""

        async def _work() -> str:
            return json.dumps(
                {
                    "state": app.engine.state.comms_state.value,
                    "links": [],
                    "note": "links emit through the comms estimator in L1",
                }
            )

        return await _wrap("comms_state", {}, ctx, _work)

    @mcp.tool()
    async def self_model_assess(question: str = "", ctx: Context | None = None) -> str:
        """Self-model capability assessment (placeholder for L1)."""

        async def _work() -> str:
            return json.dumps(
                {
                    "question": question or "default",
                    "capabilities": app.engine.state.last_capabilities,
                    "note": "self-model layer lands in L1",
                }
            )

        return await _wrap(
            "self_model_assess", {"question": question}, ctx, _work
        )

    @mcp.tool()
    async def self_estimator_status(ctx: Context | None = None) -> str:
        """Estimator covariances, last update times, divergence flags."""

        async def _work() -> str:
            return json.dumps(
                {
                    "estimators": [],
                    "note": "estimator framework lands in L1",
                }
            )

        return await _wrap("self_estimator_status", {}, ctx, _work)

    @mcp.tool()
    async def inference_local(prompt: str, ctx: Context | None = None) -> str:
        """Mock local inference (returns a fixed structured response)."""

        async def _work() -> str:
            return json.dumps(
                {
                    "model": "nous-local-mock",
                    "prompt_len": len(prompt),
                    "response": "[local mock] " + prompt[:160],
                }
            )

        return await _wrap(
            "inference_local", {"prompt_len": len(prompt)}, ctx, _work
        )

    @mcp.tool()
    async def interop_formats(ctx: Context | None = None) -> str:
        """List the interop adapters the server knows about."""

        async def _work() -> str:
            return json.dumps(
                {
                    "adapters": [
                        "cot",
                        "sensorthings",
                        "misb_klv",
                        "nmea0183",
                        "stanag_4774",
                        "mqtt",
                    ],
                    "note": "adapters ship as typed stubs in v0.1",
                }
            )

        return await _wrap("interop_formats", {}, ctx, _work)

    return mcp


_INSTRUCTIONS = """\
nous -- simulator for a man-portable AI inference appliance.

Read the runbooks under `skills/` (nous-getting-started.md first). Every
tool call is tier-classified and audited; output bodies are SHA-256 hashed,
never written to disk. The audit log path is reported by `device_info`.

Representative v0.1 tools:
  device_info / device_health / state_get / state_history
  power_status / apu_status / comms_state
  self_model_assess / self_estimator_status
  inference_local / interop_formats

The full surface (per-subsystem reads, scenario control, interop encoders)
lands in L1 (see `docs/backlog.md`).
"""
