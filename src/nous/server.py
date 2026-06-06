"""FastMCP server: the audited tool surface wired through the runner.

Every tool runs through :func:`nous.runner.run` and returns a single
bounded string. The handlers live in per-capability modules under
``nous.tools`` (ADR 0021); :func:`build_app` wires them by calling each
module's ``register(mcp, app, wrap)``. See ``docs/tool-reference.md`` for
the full surface and ``docs/backlog.md`` for the BL-NNN tracker.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
from mcp.server.fastmcp import Context, FastMCP
from starlette.applications import Starlette

from .audit import AuditLogger
from .audit_anchor import AnchorLog
from .config import Settings, get_settings
from .db import StateTransitionLog, init_db
from .engine import Engine
from .policy import PolicyMode
from .runner import run as audited_run
from .tick import tick_loop
from .tools import audit, inference, interop, meta, scenarios, self_model, state, subsystems

__all__ = [
    "Nous",
    "WrapFn",
    "attach_tick_lifespan",
    "build_app",
    "build_server",
    "tick_lifespan",
]


Work = Callable[[], Awaitable[str]]
WrapFn = Callable[[str, dict[str, Any], Context | None, Work], Awaitable[str]]


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
    """Server-wide state: settings, audit sink, engine, FastMCP server."""

    mcp: FastMCP  # the audited tool surface; attached by build_app

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditLogger(str(settings.resolved_audit_path()))
        self.anchor = AnchorLog(str(settings.resolved_anchor_path()))
        db_engine = None
        try:
            db_engine = init_db(settings.resolved_db_url())
        except Exception:  # noqa: BLE001
            db_engine = None
        self.transition_log = StateTransitionLog(db_engine)
        self.engine = Engine(
            settings=settings, transition_log=self.transition_log, audit=self.audit
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


def build_app(settings: Settings | None = None) -> Nous:
    """Construct the :class:`Nous` application (engine plus audited FastMCP).

    The tick loop is deliberately NOT registered on the MCP server
    lifespan. Under ``stateless_http`` the low-level server runs once per
    request, so a server-lifespan tick loop reboots the engine on every
    call (reset -> boot -> one tick -> shutdown); see ADR 0024. The
    returned ``Nous`` exposes ``.engine`` and ``.mcp`` so the serve
    entrypoint attaches a process-lifetime tick loop with
    :func:`attach_tick_lifespan`.
    """
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
        result = await audited_run(
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
        # Daily audit anchor (BL-031 / ADR 0026). The audit chain only
        # advances on a tool call, so the tool-call path is the right
        # cadence to pin it; ``maybe_anchor`` is a single date comparison
        # except on the first call of a new UTC day. Best-effort: anchoring
        # never breaks a tool call, matching the audit sink's posture.
        with contextlib.suppress(Exception):
            app.anchor.maybe_anchor(app.audit.path)
        return result

    meta.register(mcp, app, _wrap)

    audit.register(mcp, app, _wrap)

    state.register(mcp, app, _wrap)

    subsystems.register(mcp, app, _wrap)

    self_model.register(mcp, app, _wrap)

    inference.register(mcp, app, _wrap)

    interop.register(mcp, app, _wrap)

    scenarios.register(mcp, app, _wrap)

    app.mcp = mcp
    return app


def build_server(settings: Settings | None = None) -> FastMCP:
    """Back-compatible accessor returning just the FastMCP tool surface.

    Most callers want the whole :class:`Nous` (engine plus server) via
    :func:`build_app`; this thin wrapper keeps the historical
    ``build_server() -> FastMCP`` contract for tests and embedders.
    """
    return build_app(settings).mcp


def attach_tick_lifespan(
    starlette_app: Starlette, engine: Engine, tick_hz: float
) -> Starlette:
    """Compose ``tick_lifespan`` into a Starlette app's process lifespan.

    The streamable-HTTP app's own lifespan is the MCP session manager
    (process-lifetime). Wrapping ``tick_lifespan`` around it runs the
    engine tick loop once for the lifetime of the server process,
    decoupled from the per-request MCP session lifecycle (ADR 0024). The
    original lifespan's yielded state (if any) is passed through.
    """
    original = starlette_app.router.lifespan_context

    @asynccontextmanager
    async def _combined(scoped_app: Starlette) -> AsyncIterator[Any]:
        async with tick_lifespan(engine, tick_hz), original(scoped_app) as state:
            yield state

    starlette_app.router.lifespan_context = _combined
    return starlette_app


_INSTRUCTIONS = """\
nous -- a simulation-based digital twin of an edge-AI inference appliance.

Read the runbooks under `skills/` (nous-getting-started.md first). Every
tool call is tier-classified and audited; output bodies are SHA-256 hashed,
never written to disk. The audit log path is reported by `device_info`.

Device telemetry (T0):
  device_info / device_health / state_get / state_history / audit_summary
  audit_verify / audit_anchor_verify

Subsystem reads (T0):
  power_status / apu_status / thermal_status / compute_status / storage_status
  comms_state / comms_status / position_status / sensors_status
  biometrics_status / inference_status

Self-model and estimators (T0):
  self_model_assess / self_model_viability / self_estimator_status

Interop (T0 schema + T1 codec):
  interop_formats / interop_encode / interop_decode

Comms control (T2):
  comms_send (record a transmission of N bytes on a link) / comms_publish
  (encode a message via an interop adapter and account its bytes on the link)

Local inference and cloud cap (T0/T1):
  inference_local / anthropic_cap_status

Cloud inference (T2):
  inference_cloud (prefer the capped Anthropic path; the fallback ladder
  degrades to the local mock on cap exhaustion, comms loss, or call failure,
  so a controller always gets an answer)

Posture control (T2):
  state_transition (drive the FSM: ready -> idle, then mission / relay /
  monitoring / c2, or the recoverable safe hold; terminal fault / shutdown
  are reserved for the T3 force tools)

Terminal control (T3, irreversible):
  state_force_fault / state_force_shutdown (drive the device into the
  reset-only FAULT / SHUTDOWN posture; recover via state_transition reset
  then boot)

Scenarios and configuration (T2):
  scenario_load / scenario_inject / profile_reload

Operational recovery (T2):
  audit_resync

See `docs/tool-reference.md` for parameter shapes and tier classification,
and `docs/backlog.md` for the BL-NNN line-item tracker.
"""
