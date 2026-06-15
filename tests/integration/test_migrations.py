"""Schema migration path via scripts/migrate.py (BL-051, ADR 0037).

Alembic is the source of truth for the schema; these tests pin that the
project-standard runner produces and reverts it on a fresh database. They
drive ``scripts/migrate.py`` directly (not raw ``alembic``), so the wrapper
and the baseline migration are both covered. No network: a tmp sqlite DB via
the ``config`` fixture (``NOUS_DB_URL``).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from nous.config import Settings

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_migrate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "nous_migrate", _REPO_ROOT / "scripts" / "migrate.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATE = _load_migrate()


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_head_creates_schema(config: Settings) -> None:
    assert _MIGRATE.main(["upgrade"]) == 0
    assert {
        "state_transitions",
        "audit_entries",
        "dtn_bundles",
        "dtn_meta",
    } <= _tables(config.resolved_db_url())


def test_upgrade_stamps_head_revision(config: Settings) -> None:
    _MIGRATE.main(["upgrade"])
    # Derive head from the scripts dir so this stays valid as migrations are
    # added, rather than hard-coding the baseline revision id.
    head = ScriptDirectory.from_config(_MIGRATE.build_config()).get_current_head()
    assert head is not None
    engine = create_engine(config.resolved_db_url())
    try:
        with engine.connect() as conn:
            version = conn.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    finally:
        engine.dispose()
    assert version == head


def test_downgrade_base_drops_schema(config: Settings) -> None:
    _MIGRATE.main(["upgrade"])
    assert "state_transitions" in _tables(config.resolved_db_url())
    assert _MIGRATE.main(["downgrade", "base"]) == 0
    remaining = _tables(config.resolved_db_url())
    assert "state_transitions" not in remaining
    assert "audit_entries" not in remaining
    assert "dtn_bundles" not in remaining
    assert "dtn_meta" not in remaining


def test_upgrade_handles_percent_encoded_url(
    tmp_nous_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A percent in NOUS_DB_URL must not trip Alembic's ConfigParser."""
    from nous.config import get_settings

    monkeypatch.setenv("NOUS_DB_URL", f"sqlite:///{tmp_nous_home}/st%20ate.db")
    get_settings.cache_clear()
    assert _MIGRATE.main(["upgrade"]) == 0
