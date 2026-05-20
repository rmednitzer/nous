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

    return p


def _cmd_serve(args: argparse.Namespace) -> int:
    from .server import build_server

    cfg = get_settings()
    transport = args.transport or cfg.transport
    mcp = build_server(cfg)
    if transport == "http":
        mcp.run("streamable-http")
    else:
        mcp.run("stdio")
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
    from pathlib import Path

    import yaml

    from .scenarios.loader import load_scenario

    data = yaml.safe_load(Path(args.path).read_text(encoding="utf-8"))
    scenario = load_scenario(data)
    engine = Engine(
        scenario={
            "meta": scenario.meta,
            "steps": [step.model_dump() for step in scenario.steps],
        }
    )
    engine.start()
    for _ in range(scenario.tick_budget):
        engine.tick()
    json.dump(engine.snapshot(), sys.stdout, indent=2)
    sys.stdout.write("\n")
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
    parser.print_help()
    return 2
