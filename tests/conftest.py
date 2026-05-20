"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from nous.config import Settings, get_settings
from nous.engine import Engine


@pytest.fixture
def tmp_nous_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``NOUS_HOME`` at a fresh tmp directory and clear the cache."""
    monkeypatch.setenv("NOUS_HOME", str(tmp_path))
    monkeypatch.setenv("NOUS_AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("NOUS_DB_URL", f"sqlite:///{tmp_path / 'state.db'}")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
def config(tmp_nous_home: Path) -> Settings:
    return get_settings()


@pytest.fixture
def engine(config: Settings) -> Iterator[Engine]:
    eng = Engine(settings=config)
    eng.start()
    yield eng
    eng.stop()


@pytest.fixture(autouse=True)
def _clear_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must not pick up an ambient ANTHROPIC_API_KEY."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("NOUS_ANTHROPIC_API_KEY", raising=False)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ.pop("NOUS_ANTHROPIC_API_KEY", None)
