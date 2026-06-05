"""Tests for hardware profile loading and validation in engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from nous import engine


@pytest.fixture
def fake_profiles_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    class FakeResolvedPath:
        def __init__(self, base: Path) -> None:
            self.parents = [None, None, base]

    monkeypatch.setattr(
        "nous.engine.Path.resolve", lambda _self: FakeResolvedPath(tmp_path)
    )
    return profiles_dir


def test_load_profile_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError, match="profile YAML not found"):
        engine._load_profile("does-not-exist")


def test_load_profile_requires_mapping(fake_profiles_dir: Path) -> None:
    (fake_profiles_dir / "bad.yaml").write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must decode to a mapping"):
        engine._load_profile("bad")


def test_load_profile_requires_name_field(fake_profiles_dir: Path) -> None:
    (fake_profiles_dir / "missing-name.yaml").write_text(
        "power:\n  battery_wh: 100\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="failed schema validation"):
        engine._load_profile("missing-name")


def test_load_profile_returns_valid_profile(fake_profiles_dir: Path) -> None:
    (fake_profiles_dir / "ok.yaml").write_text(
        "name: ok\npower:\n  battery_wh: 100\n",
        encoding="utf-8",
    )

    loaded = engine._load_profile("ok")
    assert loaded["name"] == "ok"


def test_load_profile_surfaces_invalid_field_name(fake_profiles_dir: Path) -> None:
    # ADR 0029: the controller doing profile_reload must see which field was
    # invalid, so the underlying validation detail is surfaced, not discarded.
    (fake_profiles_dir / "bad-reserve.yaml").write_text(
        "name: bad\npower:\n  soc_pct_critical_threshold: oops\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="soc_pct_critical_threshold"):
        engine._load_profile("bad-reserve")


def test_load_profile_rejects_non_mapping_safety_section(fake_profiles_dir: Path) -> None:
    # A non-mapping safety section (here a list) would crash subsystem
    # construction and the tick loop; it must be refused at load instead.
    (fake_profiles_dir / "bad-power.yaml").write_text(
        "name: bad\npower:\n  - 1\n  - 2\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"power.*must be a mapping"):
        engine._load_profile("bad-power")
