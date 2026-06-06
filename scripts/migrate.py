"""Run nous schema migrations through Alembic (BL-051, ADR 0037).

Alembic is the source of truth for the schema (``alembic/versions/``). This
script is the project-standard entry point so a migration runs against the
deployment database without re-deriving the Alembic invocation by hand: the
target URL is the engine's own ``Settings.resolved_db_url`` (``NOUS_DB_URL``
or the ``$NOUS_HOME`` sqlite default), so ``scripts/migrate.py upgrade`` hits
the same database the server reads.

Examples::

    uv run python scripts/migrate.py upgrade               # to head
    uv run python scripts/migrate.py current
    uv run python scripts/migrate.py downgrade -1
    uv run python scripts/migrate.py revision -m "add x" --autogenerate
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_config() -> Config:
    """Build an Alembic config pointed at the engine's resolved database URL."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from nous.config import get_settings

    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", get_settings().resolved_db_url())
    return cfg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run nous schema migrations (Alembic).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upgrade", help="upgrade to a revision (default: head)")
    up.add_argument("revision", nargs="?", default="head")

    down = sub.add_parser("downgrade", help="downgrade to a revision (e.g. -1, base)")
    down.add_argument("revision")

    sub.add_parser("current", help="show the database's current revision")
    sub.add_parser("history", help="show the revision history")

    rev = sub.add_parser("revision", help="create a new revision")
    rev.add_argument("-m", "--message", required=True)
    rev.add_argument(
        "--autogenerate",
        action="store_true",
        help="diff SQLModel metadata against the database to seed the revision",
    )

    stamp = sub.add_parser("stamp", help="stamp a revision without running migrations")
    stamp.add_argument("revision")

    args = parser.parse_args(argv)
    cfg = build_config()

    if args.cmd == "upgrade":
        command.upgrade(cfg, args.revision)
    elif args.cmd == "downgrade":
        command.downgrade(cfg, args.revision)
    elif args.cmd == "current":
        command.current(cfg, verbose=True)
    elif args.cmd == "history":
        command.history(cfg, verbose=True)
    elif args.cmd == "revision":
        command.revision(cfg, message=args.message, autogenerate=args.autogenerate)
    elif args.cmd == "stamp":
        command.stamp(cfg, args.revision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
