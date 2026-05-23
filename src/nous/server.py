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
        # Mount the streamable-HTTP MCP transport at the root so a bare
        # custom-connector URL (https://host/) reaches the JSON-RPC endpoint
        # directly. OAuth metadata, /authorize, /token, /register and /revoke
        # are SDK-registered as siblings; no conflict at the routing layer.
        "streamable_http_path": "/",
    }
    if cfg.transport == "http" and cfg.oauth_enabled:
        from urllib.parse import urlparse

        from mcp.server.transport_security import TransportSecuritySettings

        from .auth import build_auth_settings, make_oauth_provider

        fastmcp_kwargs["auth"] = build_auth_settings(cfg.oauth_issuer)
        fastmcp_kwargs["auth_server_provider"] = make_oauth_provider(cfg)

        # MCP SDK enables DNS-rebinding protection by default and rejects
        # any Host header outside the bind address. Allowlist the public
        # hostname taken from the issuer URL plus the local bind.
        issuer_host = urlparse(cfg.oauth_issuer).hostname or ""
        bind_host = host or "127.0.0.1"
        allowed_hosts = [
            issuer_host,
            f"{issuer_host}:443",
            f"{bind_host}:{port}",
            "127.0.0.1",
            "127.0.0.1:8088",
            "localhost",
            "localhost:8088",
        ]
        allowed_origins = [
            cfg.oauth_issuer.rstrip("/"),
            "https://claude.ai",
        ]
        fastmcp_kwargs["transport_security"] = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        )

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
        """Battery state-of-charge, draw, projected endurance."""

        async def _work() -> str:
            truth = dict(app.engine.power.truth())
            estimate = app.engine.power_est.state()
            payload = {
                "soc_pct": round(truth["soc_pct"], 3),
                "voltage_v": round(truth["voltage_v"], 3),
                "current_a": round(truth["current_a"], 4),
                "load_w": round(truth["load_w"], 3),
                "charge_offered_w": round(truth["charge_offered_w"], 3),
                "charge_accepted_w": round(truth["charge_accepted_w"], 3),
                "remaining_wh": round(truth["remaining_wh"], 3),
                "endurance_min_p50": (
                    None
                    if truth["endurance_min"] is None
                    else round(truth["endurance_min"], 2)
                ),
                "flag": truth["flag"],
                "estimate": {
                    "soc_pct": round(estimate.point["soc_pct"], 3),
                    "soc_pct_sigma": round(
                        estimate.covariance["soc_pct"] ** 0.5, 4
                    ),
                    "voltage_v": round(estimate.point["voltage_v"], 3),
                },
            }
            return json.dumps(payload)

        return await _wrap("power_status", {}, ctx, _work)

    @mcp.tool()
    async def apu_status(ctx: Context | None = None) -> str:
        """Auxiliary-power-unit state (solar, fuel cell, vehicle, USB-C PD)."""

        async def _work() -> str:
            truth = dict(app.engine.apu.truth())
            estimate = app.engine.apu_est.state()
            payload = {
                "solar_w": round(truth["solar_w"], 3),
                "fuelcell_w": round(truth["fuelcell_w"], 3),
                "vehicle_w": round(truth["vehicle_w"], 3),
                "usbc_w": round(truth["usbc_w"], 3),
                "total_w": round(truth["total_w"], 3),
                "fuelcell_fuel_g": round(truth["fuel_g"], 3),
                "fuelcell_fuel_pct": round(truth["fuel_pct"], 3),
                "vehicle_connected": truth["vehicle_connected"],
                "usbc_connected": truth["usbc_connected"],
                "usbc_profile_w": round(truth["usbc_profile_w"], 3),
                "estimate": {
                    "total_w": round(estimate.point["total_w"], 3),
                    "total_w_sigma": round(
                        estimate.covariance["total_w"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await _wrap("apu_status", {}, ctx, _work)

    @mcp.tool()
    async def thermal_status(ctx: Context | None = None) -> str:
        """Two-state thermal model (junction + enclosure + ambient)."""

        async def _work() -> str:
            truth = dict(app.engine.thermal.truth())
            estimate = app.engine.thermal_est.state()
            payload = {
                "junction_c": round(truth["junction_c"], 3),
                "enclosure_c": round(truth["enclosure_c"], 3),
                "ambient_c": round(truth["ambient_c"], 3),
                "load_w": round(truth["load_w"], 3),
                "headroom_c": round(truth["headroom_c"], 3),
                "throttling": truth["throttling"],
                "junction_temp_throttle": round(truth["junction_temp_throttle"], 3),
                "junction_temp_max": round(truth["junction_temp_max"], 3),
                "estimate": {
                    "junction_c": round(estimate.point["junction_c"], 3),
                    "junction_c_sigma": round(
                        estimate.covariance["junction_c"] ** 0.5, 4
                    ),
                    "enclosure_c": round(estimate.point["enclosure_c"], 3),
                    "enclosure_c_sigma": round(
                        estimate.covariance["enclosure_c"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await _wrap("thermal_status", {}, ctx, _work)

    @mcp.tool()
    async def compute_status(ctx: Context | None = None) -> str:
        """Compute subsystem: load fraction, electrical draw, throttling."""

        async def _work() -> str:
            truth = dict(app.engine.compute.truth())
            estimate = app.engine.compute_est.state()
            payload = {
                "load_pct": round(truth["load_pct"], 3),
                "requested_load_pct": round(truth["requested_load_pct"], 3),
                "draw_w": round(truth["draw_w"], 3),
                "draw_w_idle": round(truth["draw_w_idle"], 3),
                "draw_w_load": round(truth["draw_w_load"], 3),
                "throttled": truth["throttled"],
                "saturated": truth["saturated"],
                "tok_per_s_capacity": round(truth["tok_per_s_capacity"], 3),
                "estimate": {
                    "load_pct": round(estimate.point["load_pct"], 3),
                    "load_pct_sigma": round(
                        estimate.covariance["load_pct"] ** 0.5, 4
                    ),
                    "draw_w": round(estimate.point["draw_w"], 3),
                    "draw_w_sigma": round(
                        estimate.covariance["draw_w"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await _wrap("compute_status", {}, ctx, _work)

    @mcp.tool()
    async def storage_status(ctx: Context | None = None) -> str:
        """Storage subsystem: capacity, used, wear, write rate."""

        async def _work() -> str:
            truth = dict(app.engine.storage.truth())
            estimate = app.engine.storage_est.state()
            payload = {
                "capacity_gib": round(truth["capacity_gib"], 3),
                "used_gib": round(truth["used_gib"], 3),
                "free_gib": round(truth["free_gib"], 3),
                "used_pct": round(truth["used_pct"], 3),
                "wear_pct": round(truth["wear_pct"], 4),
                "lifetime_physical_gib": round(truth["lifetime_physical_gib"], 3),
                "write_rate_gib_per_s": round(truth["write_rate_gib_per_s"], 4),
                "at_capacity": truth["at_capacity"],
                "worn_out": truth["worn_out"],
                "estimate": {
                    "used_gib": round(estimate.point["used_gib"], 3),
                    "used_gib_sigma": round(
                        estimate.covariance["used_gib"] ** 0.5, 4
                    ),
                    "wear_pct": round(estimate.point["wear_pct"], 4),
                    "wear_pct_sigma": round(
                        estimate.covariance["wear_pct"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await _wrap("storage_status", {}, ctx, _work)

    @mcp.tool()
    async def comms_state(ctx: Context | None = None) -> str:
        """Comms-stack summary (per ADR-0006)."""

        async def _work() -> str:
            label, reason = app.engine.comms.derive_state()
            links = [link.model_dump() for link in app.engine.comms.link_estimates()]
            return json.dumps(
                {
                    "state": label.value,
                    "reason": reason,
                    "links": links,
                }
            )

        return await _wrap("comms_state", {}, ctx, _work)

    @mcp.tool()
    async def comms_status(ctx: Context | None = None) -> str:
        """Comms subsystem: per-link envelope, live RSSI, loss, throughput, age."""

        async def _work() -> str:
            truth = dict(app.engine.comms.truth())
            label, reason = app.engine.comms.derive_state()
            payload = {
                "state": label.value,
                "reason": reason,
                "link_count": len(truth["links"]),
                "links": truth["links"],
            }
            return json.dumps(payload)

        return await _wrap("comms_status", {}, ctx, _work)

    @mcp.tool()
    async def position_status(ctx: Context | None = None) -> str:
        """Position subsystem: lat/lon/alt ground truth, fix state, drift."""

        async def _work() -> str:
            truth = dict(app.engine.position.truth())
            estimate = app.engine.position_est.state()
            payload = {
                "lat": round(truth["lat"], 6),
                "lon": round(truth["lon"], 6),
                "alt_m": round(truth["alt_m"], 3),
                "speed_mps": round(truth["speed_mps"], 3),
                "heading_deg": round(truth["heading_deg"], 3),
                "vertical_mps": round(truth["vertical_mps"], 3),
                "has_fix": truth["has_fix"],
                "dead_reckoning_s": round(truth["dead_reckoning_s"], 3),
                "fix_rate_hz": round(truth["fix_rate_hz"], 3),
                "estimate": {
                    "lat": round(estimate.point.get("lat", 0.0), 6),
                    "lon": round(estimate.point.get("lon", 0.0), 6),
                    "alt_m": round(estimate.point.get("alt_m", 0.0), 3),
                    "lat_sigma": round(
                        estimate.covariance.get("lat", 0.0) ** 0.5, 8
                    ),
                    "lon_sigma": round(
                        estimate.covariance.get("lon", 0.0) ** 0.5, 8
                    ),
                    "alt_sigma_m": round(
                        estimate.covariance.get("alt_m", 0.0) ** 0.5, 4
                    ),
                    "rejected_updates": app.engine.position_est.rejected_updates,
                },
            }
            return json.dumps(payload)

        return await _wrap("position_status", {}, ctx, _work)

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
            rows = []
            for est in (
                app.engine.power_est,
                app.engine.apu_est,
                app.engine.thermal_est,
                app.engine.compute_est,
                app.engine.storage_est,
                app.engine.comms_est,
                app.engine.position_est,
            ):
                state = est.state()
                rows.append(
                    {
                        "source": state.source,
                        "ts_s": round(state.ts_s, 3),
                        "point": {k: round(v, 4) for k, v in state.point.items()},
                        "covariance": {
                            k: round(float(v), 6) for k, v in state.covariance.items()
                        },
                    }
                )
            return json.dumps({"estimators": rows})

        return await _wrap("self_estimator_status", {}, ctx, _work)

    @mcp.tool()
    async def inference_local(
        prompt: str,
        max_tokens: int = 128,
        ctx: Context | None = None,
    ) -> str:
        """Local-path inference. Returns the synthetic response plus latency,
        energy joules, and the token-rate the profile would have delivered."""

        async def _work() -> str:
            result = app.engine.inference.request_local(
                prompt, max_tokens=max_tokens
            )
            payload = {"model": "nous-local-mock", "prompt_len": len(prompt)}
            payload.update(result.to_dict())
            return json.dumps(payload)

        return await _wrap(
            "inference_local",
            {"prompt_len": len(prompt), "max_tokens": int(max_tokens)},
            ctx,
            _work,
        )

    @mcp.tool()
    async def inference_status(ctx: Context | None = None) -> str:
        """Inference subsystem totals: calls, tokens, joules, last latency."""

        async def _work() -> str:
            truth = dict(app.engine.inference.truth())
            payload = {
                "local_calls": truth["local_calls"],
                "total_tokens": truth["total_tokens"],
                "total_energy_j": round(truth["total_energy_j"], 4),
                "last_latency_s": round(truth["last_latency_s"], 4),
                "last_rate_tok_per_s": round(truth["last_rate_tok_per_s"], 3),
                "tok_per_s_capacity": round(truth["tok_per_s_capacity"], 3),
                "energy_j_per_tok": round(truth["energy_j_per_tok"], 4),
                "continuous_rate": round(truth["continuous_rate"], 3),
            }
            return json.dumps(payload)

        return await _wrap("inference_status", {}, ctx, _work)

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
  power_status / apu_status / thermal_status / compute_status / comms_state
  self_model_assess / self_estimator_status
  inference_local / interop_formats

The full surface (per-subsystem reads, scenario control, interop encoders)
lands in L1 (see `docs/backlog.md`).
"""
