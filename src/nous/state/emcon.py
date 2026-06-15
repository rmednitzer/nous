"""EMCON emission-control postures (BL-060, ADR 0065 and ADR 0066).

EMCON (emission control) is an orthogonal, operator-imposed posture, like the
operator and comms states: it gates which comms links may emit, independent of
physical link health, so the audit can tell "the operator silenced us" from "the
link is physically dead". A named emission profile lists the links permitted to
transmit; the device emits on a link only when the active profile permits it.

Two profiles are always available: ``unrestricted`` (every configured link) and
``silent`` (no link, full radio silence). Further named profiles come from an
optional ``comms.emcon`` profile section, so a profile without one leaves EMCON
unrestricted and inert, exactly as before.

A profile may also carry a duty-cycle emission ``window`` (ADR 0066): its links
emit only inside a scheduled burst (``on_s`` open out of every ``period_s``,
offset by ``phase_s``) and stay silent between bursts. The window is evaluated
against the injected ``now_s`` sim clock, so a send offered between bursts is
held in the store-and-forward outbox and ships when the next burst opens.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["SILENT", "UNRESTRICTED", "Emcon"]

UNRESTRICTED = "unrestricted"
SILENT = "silent"


@dataclass(frozen=True)
class _Window:
    """A periodic duty cycle: ``on_s`` seconds open out of every ``period_s``."""

    period_s: float
    on_s: float
    phase_s: float = 0.0

    def open_at(self, now_s: float) -> bool:
        return (now_s - self.phase_s) % self.period_s < self.on_s


class Emcon:
    """The active emission posture over a set of named profiles."""

    def __init__(self, comms_cfg: Mapping[str, Any] | None = None) -> None:
        all_links = _links_from_cfg(comms_cfg)
        section = comms_cfg.get("emcon") if isinstance(comms_cfg, Mapping) else None
        self.configured: bool = isinstance(section, Mapping) and bool(section)
        self._all: set[str] = set(all_links)
        self._profiles: dict[str, set[str]] = {
            UNRESTRICTED: set(all_links),
            SILENT: set(),
        }
        self._windows: dict[str, _Window] = {}
        default = UNRESTRICTED
        if isinstance(section, Mapping):
            raw_profiles = section.get("profiles")
            if isinstance(raw_profiles, Mapping):
                for name, body in raw_profiles.items():
                    if isinstance(name, str) and name.strip():
                        key = name.strip()
                        self._profiles[key] = _parse_links(body, all_links)
                        window = _parse_window(body)
                        if window is not None:
                            self._windows[key] = window
            raw_default = section.get("default")
            if isinstance(raw_default, str) and raw_default.strip() in self._profiles:
                default = raw_default.strip()
        self._active = default

    def permits(self, link_id: str, now_s: float | None = None) -> bool:
        """Whether the active profile lets the device emit on ``link_id`` now.

        Membership in the active profile is necessary; a profile that carries a
        duty-cycle window additionally requires ``now_s`` to fall inside an open
        burst. With no window, or no ``now_s`` to place against the schedule, the
        check is membership-only, so an unwindowed posture behaves as before.
        """
        if link_id not in self._profiles.get(self._active, self._all):
            return False
        window = self._windows.get(self._active)
        if window is None or now_s is None:
            return True
        return window.open_at(now_s)

    @property
    def active(self) -> str:
        return self._active

    def set_profile(self, name: str) -> bool:
        """Activate a named profile. False (and no change) if it is unknown.

        The name is stripped to match the config-loaded profile names, so stray
        whitespace from a tool call does not defeat an otherwise valid match.
        """
        key = name.strip()
        if key in self._profiles:
            self._active = key
            return True
        return False

    def status(self, now_s: float | None = None) -> dict[str, Any]:
        """The read surface for the ``emcon_status`` tool."""
        window = self._windows.get(self._active)
        permitted = self._profiles.get(self._active, self._all)
        in_window = window is None or now_s is None or window.open_at(now_s)
        return {
            "active": self._active,
            "configured": self.configured,
            "permitted_links": sorted(permitted),
            "emitting": bool(permitted) and in_window,
            "window": _window_dict(window),
            "profiles": {
                name: sorted(links) for name, links in sorted(self._profiles.items())
            },
            "windows": {
                name: _window_dict(w) for name, w in sorted(self._windows.items())
            },
        }


def _links_from_cfg(comms_cfg: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(comms_cfg, Mapping):
        return []
    raw = comms_cfg.get("links")
    out: list[str] = []
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, Mapping):
                lid = entry.get("id") or entry.get("link_id")
                if isinstance(lid, str) and lid.strip():
                    out.append(lid.strip())
    return out


def _parse_links(body: Any, all_links: list[str]) -> set[str]:
    raw = (
        body.get("permit_links", body.get("links"))
        if isinstance(body, Mapping)
        else body
    )
    configured = set(all_links)
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ("all", "*"):
            return configured
        if low in ("none", ""):
            return set()
        return {raw.strip()} & configured
    if isinstance(raw, (list, tuple)):
        parsed = {x.strip() for x in raw if isinstance(x, str) and x.strip()}
        return parsed & configured
    return set()


def _parse_window(body: Any) -> _Window | None:
    if not isinstance(body, Mapping):
        return None
    raw = body.get("window")
    if not isinstance(raw, Mapping):
        return None
    period = _as_float(raw.get("period_s"))
    on = _as_float(raw.get("on_s"))
    phase = _as_float(raw.get("phase_s"))
    if period is None or on is None:
        return None
    if period > 0.0 and 0.0 < on < period:
        return _Window(period_s=period, on_s=on, phase_s=phase or 0.0)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _window_dict(window: _Window | None) -> dict[str, float] | None:
    if window is None:
        return None
    return {"period_s": window.period_s, "on_s": window.on_s, "phase_s": window.phase_s}
