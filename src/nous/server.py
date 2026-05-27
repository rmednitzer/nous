"""FastMCP server: representative tools wired through the audited runner.

Every tool runs through :func:`nous.runner.run`. The handler returns a
single bounded string. The tools registered here are the *representative*
v0.1 surface; full subsystem coverage lands in L1 (see ``docs/backlog.md``).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
from mcp.server.fastmcp import Context, FastMCP

from . import __version__
from .audit import AuditLogger
from .config import Settings, get_settings
from .db import StateTransitionLog, init_db
from .engine import Engine
from .policy import PolicyMode
from .runner import run as audited_run
from .tick import tick_loop

__all__ = ["Nous", "build_server", "tick_lifespan"]


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
        db_engine = None
        try:
            db_engine = init_db(settings.resolved_db_url())
        except Exception:  # noqa: BLE001
            db_engine = None
        self.transition_log = StateTransitionLog(db_engine)
        self.engine = Engine(
            settings=settings, transition_log=self.transition_log
        )
        self.engine.start()

    @property
    def policy_mode(self) -> PolicyMode:
        return PolicyMode(self.settings.policy)


@asynccontextmanager
async def tick_lifespan(
    engine: Engine, tick_hz: float
) -> AsyncIterator[None]:
    """Run ``tick_loop`` for the lifetime of the context.

    On entry, spawn a background task that advances ``engine.tick()`` at
    ``tick_hz``. On exit, set the stop event so the task drains cleanly,
    then call ``engine.stop()`` so the FSM lands on SHUTDOWN rather than
    leaking the running state. ``engine.stop()`` runs in a ``finally``
    so a crashed tick task (or a cancelled task group) still surrenders
    the engine cleanly. Closes AUDIT-2026-05-23 C3 (engine starts but
    the FastMCP server never ticks it).
    """
    stop = anyio.Event()
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(tick_loop, engine, tick_hz, stop)
            try:
                yield
            finally:
                stop.set()
    finally:
        engine.stop()


def build_server(settings: Settings | None = None) -> FastMCP:
    """Construct the FastMCP server with every tool registered."""
    cfg = settings or get_settings()
    app = Nous(cfg)

    @asynccontextmanager
    async def _lifespan(_server: FastMCP[None]) -> AsyncIterator[None]:
        async with tick_lifespan(app.engine, cfg.tick_hz):
            yield

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
        "lifespan": _lifespan,
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

        return await _wrap("audit_resync", {}, ctx, _work)

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

        return await _wrap("state_get", {}, ctx, _work)

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
    async def sensors_status(ctx: Context | None = None) -> str:
        """Environmental sensor pack: ambient temp, humidity, baro pressure."""

        async def _work() -> str:
            truth = dict(app.engine.sensors.truth())
            estimate = app.engine.sensors_est.state()
            payload = {
                "temp_c": round(truth["temp_c"], 3),
                "humidity_pct": round(truth["humidity_pct"], 3),
                "baro_kpa": round(truth["baro_kpa"], 3),
                "estimate": {
                    "temp_c": round(estimate.point.get("temp_c", 0.0), 3),
                    "temp_c_sigma": round(
                        estimate.covariance.get("temp_c", 0.0) ** 0.5, 4
                    ),
                    "humidity_pct": round(
                        estimate.point.get("humidity_pct", 0.0), 3
                    ),
                    "humidity_pct_sigma": round(
                        estimate.covariance.get("humidity_pct", 0.0) ** 0.5, 4
                    ),
                    "baro_kpa": round(estimate.point.get("baro_kpa", 0.0), 3),
                    "baro_kpa_sigma": round(
                        estimate.covariance.get("baro_kpa", 0.0) ** 0.5, 4
                    ),
                    "rejected_updates": app.engine.sensors_est.rejected_updates,
                },
            }
            return json.dumps(payload)

        return await _wrap("sensors_status", {}, ctx, _work)

    @mcp.tool()
    async def biometrics_status(ctx: Context | None = None) -> str:
        """Operator biometrics: heart rate, core temp, hydration, cognitive load."""

        async def _work() -> str:
            truth = dict(app.engine.biometrics.truth())
            estimate = app.engine.biometrics_est.state()
            payload = {
                "heart_rate_bpm": round(truth["heart_rate_bpm"], 2),
                "core_temp_c": round(truth["core_temp_c"], 3),
                "hydration_pct": round(truth["hydration_pct"], 2),
                "cognitive_load": round(truth["cognitive_load"], 3),
                "estimate": {
                    "heart_rate_bpm": round(
                        estimate.point.get("heart_rate_bpm", 0.0), 2
                    ),
                    "heart_rate_bpm_sigma": round(
                        estimate.covariance.get("heart_rate_bpm", 0.0) ** 0.5, 3
                    ),
                    "core_temp_c": round(estimate.point.get("core_temp_c", 0.0), 3),
                    "core_temp_c_sigma": round(
                        estimate.covariance.get("core_temp_c", 0.0) ** 0.5, 4
                    ),
                    "hydration_pct": round(
                        estimate.point.get("hydration_pct", 0.0), 2
                    ),
                    "hydration_pct_sigma": round(
                        estimate.covariance.get("hydration_pct", 0.0) ** 0.5, 3
                    ),
                    "cognitive_load": round(
                        estimate.point.get("cognitive_load", 0.0), 3
                    ),
                    "cognitive_load_sigma": round(
                        estimate.covariance.get("cognitive_load", 0.0) ** 0.5, 4
                    ),
                    "rejected_updates": app.engine.biometrics_est.rejected_updates,
                },
            }
            return json.dumps(payload)

        return await _wrap("biometrics_status", {}, ctx, _work)

    @mcp.tool()
    async def self_model_assess(question: str = "", ctx: Context | None = None) -> str:
        """Self-model capability assessment with calibrated p5/p50/p95 bands."""

        async def _work() -> str:
            from .self_model.assess import assess
            from .self_model.explain import explain

            a = assess(question, engine=app.engine)
            payload = {
                "question": a.question,
                "capabilities": {
                    cap.name: cap.model_dump()
                    for cap in (
                        a.endurance,
                        a.thermal_headroom,
                        a.inference_capacity,
                    )
                    if cap is not None
                },
                "explanation": explain(a),
            }
            return json.dumps(payload)

        return await _wrap(
            "self_model_assess", {"question": question}, ctx, _work
        )

    @mcp.tool()
    async def self_model_viability(
        task: str,
        endurance_min: float | None = None,
        thermal_headroom_c: float | None = None,
        inference_tok_per_s: float | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Decide whether a task is feasible against the current capabilities."""

        async def _work() -> str:
            from .self_model.assess import assess
            from .self_model.viability import viability

            requirements: dict[str, float] = {}
            if endurance_min is not None:
                requirements["endurance_min"] = float(endurance_min)
            if thermal_headroom_c is not None:
                requirements["thermal_headroom_c"] = float(thermal_headroom_c)
            if inference_tok_per_s is not None:
                requirements["inference_tok_per_s"] = float(inference_tok_per_s)

            a = assess(task, engine=app.engine)
            v = viability(a, task, requirements=requirements or None)
            return json.dumps(
                {
                    "task": task,
                    "feasible": v.feasible,
                    "confidence": v.confidence,
                    "reason": v.reason,
                    "requirements": requirements,
                }
            )

        return await _wrap(
            "self_model_viability",
            {
                "task": task,
                "endurance_min": endurance_min,
                "thermal_headroom_c": thermal_headroom_c,
                "inference_tok_per_s": inference_tok_per_s,
            },
            ctx,
            _work,
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
                app.engine.sensors_est,
                app.engine.biometrics_est,
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
    async def anthropic_cap_status(ctx: Context | None = None) -> str:
        """Surface the Anthropic daily call cap (BL-021).

        Returns a structured payload a self-driving controller can branch
        on: ``available`` says whether a cloud call would even be
        attempted (key configured + cap not exhausted); ``remaining``
        is the count today's budget will still admit. ``exhausted=true``
        is the signal to fall back to ``inference_local``.
        """

        async def _work() -> str:
            from .anthropic_status import cap_status

            payload = cap_status(cfg)
            return json.dumps(payload)

        return await _wrap("anthropic_cap_status", {}, ctx, _work)

    @mcp.tool()
    async def interop_formats(ctx: Context | None = None) -> str:
        """List the interop adapters the server knows about."""

        async def _work() -> str:
            from .interop import REGISTRY

            return json.dumps(
                {
                    "adapters": sorted(REGISTRY.keys()),
                    "note": "adapters live in src/nous/interop/",
                }
            )

        return await _wrap("interop_formats", {}, ctx, _work)

    @mcp.tool()
    async def interop_encode(
        adapter: str,
        data: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Encode ``data`` via the named interop adapter (BL-041 / T1).

        Returns a structured response: ``{"adapter": ..., "payload_hex":
        ..., "len": N}`` on success or ``{"error": ...}`` on a
        StaleEstimateError or schema failure. The payload is hex-encoded
        so the wire bytes survive an MCP JSON-RPC trip without
        codec-related corruption.
        """

        async def _work() -> str:
            from .interop import StaleEstimateError, build_adapter

            try:
                impl = build_adapter(adapter)
            except KeyError as exc:
                return json.dumps({"error": str(exc)})
            try:
                payload = impl.encode(dict(data or {}))
            except StaleEstimateError as exc:
                return json.dumps(
                    {
                        "adapter": adapter,
                        "error": "stale_estimate",
                        "age_s": exc.age_s,
                        "max_age_s": exc.max_age_s,
                    }
                )
            except (ValueError, TypeError) as exc:
                return json.dumps({"adapter": adapter, "error": str(exc)})
            return json.dumps(
                {
                    "adapter": adapter,
                    "payload_hex": payload.hex(),
                    "len": len(payload),
                }
            )

        return await _wrap(
            "interop_encode", {"adapter": adapter, "data": dict(data or {})}, ctx, _work
        )

    @mcp.tool()
    async def interop_decode(
        adapter: str,
        payload_hex: str,
        ctx: Context | None = None,
    ) -> str:
        """Decode a hex-encoded payload via the named adapter (BL-041 / T1).

        Returns the adapter's structured decode output as JSON. Hex
        decoding errors and unknown adapter names return ``{"error":
        ...}``; an adapter's own ``{"error": ...}`` decode response
        passes through unchanged.
        """

        async def _work() -> str:
            from .interop import build_adapter

            try:
                impl = build_adapter(adapter)
            except KeyError as exc:
                return json.dumps({"error": str(exc)})
            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError as exc:
                return json.dumps({"adapter": adapter, "error": f"hex: {exc}"})
            decoded = impl.decode(payload)
            return json.dumps({"adapter": adapter, "decoded": dict(decoded)})

        return await _wrap(
            "interop_decode",
            {"adapter": adapter, "payload_hex_len": len(payload_hex)},
            ctx,
            _work,
        )

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

        return await _wrap("profile_reload", {"name": name}, ctx, _work)

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
            from .scenarios import load_scenario_file, run_scenario

            scenario = load_scenario_file(path)
            reloaded_from = ""
            if scenario.profile and scenario.profile != app.engine.settings.profile:
                reloaded_from = app.engine.settings.profile
                app.engine.reload_profile(name=scenario.profile)
            report = dict(run_scenario(app.engine, scenario))
            if reloaded_from:
                report["profile_reloaded_from"] = reloaded_from
            return json.dumps(report)

        return await _wrap("scenario_load", {"path": path}, ctx, _work)

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
            from .scenarios.injectors import apply_injection

            outcome = apply_injection(app.engine, action, args or {})
            return json.dumps(outcome)

        return await _wrap(
            "scenario_inject",
            {"action": action, "args": dict(args or {})},
            ctx,
            _work,
        )

    return mcp


_INSTRUCTIONS = """\
nous -- simulator for a man-portable AI inference appliance.

Read the runbooks under `skills/` (nous-getting-started.md first). Every
tool call is tier-classified and audited; output bodies are SHA-256 hashed,
never written to disk. The audit log path is reported by `device_info`.

Device telemetry (T0):
  device_info / device_health / state_get / state_history

Subsystem reads (T0):
  power_status / apu_status / thermal_status / compute_status / storage_status
  comms_state / comms_status / position_status / sensors_status
  biometrics_status / inference_status

Self-model and estimators (T0):
  self_model_assess / self_model_viability / self_estimator_status

Interop (T0 schema + T1 codec):
  interop_formats / interop_encode / interop_decode

Local inference and cloud cap (T0/T1):
  inference_local / anthropic_cap_status

Scenarios and configuration (T2):
  scenario_load / scenario_inject / profile_reload

Operational recovery (T2):
  audit_resync

See `docs/tool-reference.md` for parameter shapes and tier classification,
and `docs/backlog.md` for the BL-NNN line-item tracker.
"""
