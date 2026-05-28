"""Command-line entry point for the simulator.

Subcommands:

* ``serve`` -- start the MCP server (stdio by default; HTTP if configured)
* ``tick``  -- run N ticks of the engine headlessly
* ``scenario`` -- load and run a scenario YAML

The argparse layout is intentionally flat so completion is predictable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from . import __version__
from .config import get_settings
from .engine import Engine

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nous", description="nous simulator CLI")
    p.add_argument("--version", action="version", version=f"nous {__version__}")

    sub = p.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the MCP server")
    serve.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default=None,
        help="override NOUS_TRANSPORT",
    )

    tick = sub.add_parser("tick", help="run N ticks of the engine headlessly")
    tick.add_argument("-n", "--ticks", type=int, default=10, help="ticks to run")

    scen = sub.add_parser("scenario", help="load and run a scenario YAML")
    scen.add_argument("path", help="path to the scenario YAML")

    sub.add_parser(
        "flush",
        help=(
            "flush audit + SQLite WAL to stable storage and exit "
            "(called by deploy/systemd/nous-state-flush.service)"
        ),
    )

    return p


def _cmd_serve(args: argparse.Namespace) -> int:
    import anyio

    from .server import attach_tick_lifespan, build_app, tick_lifespan

    cfg = get_settings()
    transport = args.transport or cfg.transport
    nous = build_app(cfg)
    engine = nous.engine
    mcp = nous.mcp

    if transport == "http":
        import uvicorn

        # Run the engine tick loop for the process lifetime via the
        # Starlette app lifespan, not the per-request MCP server lifespan
        # (ADR 0024: stateless_http runs the low-level server once per
        # request, so a server-lifespan loop reboots the engine each call).
        starlette_app = attach_tick_lifespan(
            mcp.streamable_http_app(), engine, cfg.tick_hz
        )
        config = uvicorn.Config(
            starlette_app,
            host=mcp.settings.host,
            port=mcp.settings.port,
            log_level=mcp.settings.log_level.lower(),
        )

        async def _serve_http() -> None:
            await uvicorn.Server(config).serve()

        anyio.run(_serve_http)
    else:

        async def _serve_stdio() -> None:
            async with tick_lifespan(engine, cfg.tick_hz):
                await mcp.run_stdio_async()

        anyio.run(_serve_stdio)
    return 0


def _cmd_tick(args: argparse.Namespace) -> int:
    engine = Engine()
    engine.start()
    for _ in range(max(1, int(args.ticks))):
        engine.tick()
    json.dump(engine.snapshot(), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_scenario(args: argparse.Namespace) -> int:
    from .scenarios import load_scenario_file, run_scenario

    scenario = load_scenario_file(args.path)
    cfg = get_settings()
    if scenario.profile and scenario.profile != cfg.profile:
        cfg = cfg.model_copy(update={"profile": scenario.profile})
    engine = Engine(
        settings=cfg,
        scenario={
            "meta": scenario.meta,
            "steps": [step.model_dump() for step in scenario.steps],
        },
    )
    engine.start()
    report = run_scenario(engine, scenario)
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _cmd_flush(_args: argparse.Namespace) -> int:
    """Force a checkpoint of the SQLite WAL and fsync the audit log.

    The systemd ``nous-state-flush.service`` runs this on a daily timer.
    The point is bounded disk thrashing: a single ``PRAGMA wal_checkpoint``
    each day plus an audit fsync, rather than syncing on every tick.
    """
    from sqlalchemy import text

    from .audit import AuditLogger
    from .db import make_engine

    cfg = get_settings()
    engine = make_engine(cfg.resolved_db_url())
    with engine.begin() as conn:
        conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
    engine.dispose()
    audit = AuditLogger(str(cfg.resolved_audit_path()))
    audit.flush()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve" or args.command is None:
        return _cmd_serve(args)
    if args.command == "tick":
        return _cmd_tick(args)
    if args.command == "scenario":
        return _cmd_scenario(args)
    if args.command == "flush":
        return _cmd_flush(args)
    parser.print_help()
    return 2
