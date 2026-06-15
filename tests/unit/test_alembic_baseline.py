"""Sanity tests for the BL-015 Alembic baseline migration."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"


@pytest.fixture
def alembic_cfg(tmp_path: Path) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url", f"sqlite:///{tmp_path / 'state.db'}"
    )
    return cfg


def test_baseline_revision_is_first() -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    scripts = ScriptDirectory.from_config(cfg)
    # History stays linear (a single head) as migrations are added on top.
    assert len(scripts.get_heads()) == 1
    # 0001_baseline remains the root revision: the only one with no down_revision.
    assert list(scripts.get_bases()) == ["0001_baseline"]
    base = scripts.get_revision("0001_baseline")
    assert base is not None and base.down_revision is None


def test_baseline_upgrade_creates_tables(alembic_cfg: Config, tmp_path: Path) -> None:
    from alembic.command import upgrade

    upgrade(alembic_cfg, "head")
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"state_transitions", "audit_entries", "alembic_version"}.issubset(tables)

    cols = {c["name"] for c in insp.get_columns("state_transitions")}
    assert {"id", "ts", "from_mode", "to_mode", "trigger", "reason"} == cols

    cols = {c["name"] for c in insp.get_columns("audit_entries")}
    assert {
        "id",
        "ts",
        "tool",
        "tier",
        "denied",
        "output_sha256",
        "output_len",
        "exit_code",
        "request_id",
        "client_id",
    } == cols


def test_baseline_downgrade_drops_tables(alembic_cfg: Config, tmp_path: Path) -> None:
    from alembic.command import downgrade, upgrade

    upgrade(alembic_cfg, "head")
    downgrade(alembic_cfg, "base")

    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert "state_transitions" not in tables
    assert "audit_entries" not in tables


def test_baseline_idempotent_against_init_db(
    alembic_cfg: Config, tmp_path: Path
) -> None:
    """init_db creates the same schema; upgrade head must not 'table exists' on top."""
    from alembic.command import upgrade

    from nous.db import init_db

    db_url = f"sqlite:///{tmp_path / 'state.db'}"
    init_db(db_url)
    upgrade(alembic_cfg, "head")

    engine = create_engine(db_url)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert {"state_transitions", "audit_entries", "alembic_version"}.issubset(tables)
