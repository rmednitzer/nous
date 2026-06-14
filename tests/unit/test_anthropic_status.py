"""Unit tests for BL-021 Anthropic cap surfacing."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from nous.anthropic_client import CallCap, CapExhausted
from nous.anthropic_status import cap_exhausted_payload, cap_status
from nous.config import Settings


def _settings(tmp_path: Path, *, cap: int = 5, key: str | None = "test-key") -> Settings:
    return Settings(
        home=tmp_path,
        anthropic_daily_cap=cap,
        anthropic_api_key=SecretStr(key) if key else None,
    )


def test_cap_status_reports_fresh_counter(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    payload = cap_status(settings)
    assert payload["available"] is True
    assert payload["count_today"] == 0
    assert payload["cap"] == 5
    assert payload["remaining"] == 5
    assert payload["exhausted"] is False
    assert payload["corrupt"] is False
    assert payload["api_key_configured"] is True


def test_cap_status_reports_corrupt_counter(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cap=5)
    (tmp_path / ".anthropic_daily_count").write_text("not valid json")
    payload = cap_status(settings)
    assert payload["corrupt"] is True
    assert payload["available"] is False
    assert payload["exhausted"] is True
    assert payload["remaining"] == 0
    assert payload["count_today"] is None


def test_cap_status_corrupt_overrides_disabled_cap(tmp_path: Path) -> None:
    # increment() refuses a corrupt counter even when the cap is disabled (the
    # corruption check precedes the cap check), so the status must not report
    # the cap as merely disabled-and-available.
    settings = _settings(tmp_path, cap=0)
    (tmp_path / ".anthropic_daily_count").write_text("{garbage")
    payload = cap_status(settings)
    assert payload["corrupt"] is True
    assert payload["available"] is False
    assert payload["exhausted"] is True


def test_cap_status_reflects_increment(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cap=2)
    cap = CallCap(tmp_path / ".anthropic_daily_count", cap=2)
    cap.increment()
    payload = cap_status(settings)
    assert payload["count_today"] == 1
    assert payload["remaining"] == 1
    assert payload["exhausted"] is False


def test_cap_status_exhausted_when_at_cap(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cap=1)
    cap = CallCap(tmp_path / ".anthropic_daily_count", cap=1)
    cap.increment()
    payload = cap_status(settings)
    assert payload["exhausted"] is True
    assert payload["available"] is False
    assert payload["remaining"] == 0


def test_cap_status_disabled_when_cap_zero(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cap=0)
    payload = cap_status(settings)
    assert payload["cap_disabled"] is True
    assert payload["remaining"] is None
    assert payload["available"] is True


def test_cap_status_reports_unavailable_without_key(tmp_path: Path) -> None:
    settings = _settings(tmp_path, key=None)
    payload = cap_status(settings)
    assert payload["available"] is False
    assert payload["api_key_configured"] is False


def test_cap_exhausted_payload_carries_reason_and_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path, cap=1)
    cap = CallCap(tmp_path / ".anthropic_daily_count", cap=1)
    cap.increment()
    with pytest.raises(CapExhausted) as raised:
        cap.increment()
    payload = cap_exhausted_payload(raised.value, settings=settings)
    assert payload["exhausted"] is True
    assert payload["kind"] == "cap_exhausted"
    assert "reason" in payload
    assert payload["cap"] == 1
    assert payload["count_today"] == 1
    assert payload["remaining"] == 0


def test_cap_exhausted_payload_without_settings_omits_snapshot(tmp_path: Path) -> None:
    exc = CapExhausted("daily Anthropic call cap reached (5/5)")
    payload = cap_exhausted_payload(exc)
    assert payload["exhausted"] is True
    assert "cap" not in payload
    assert payload["reason"] == "daily Anthropic call cap reached (5/5)"
