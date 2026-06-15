"""EMCON emission-control postures (BL-060 increment 1, ADR 0065).

EMCON (emission control) is an orthogonal, operator-imposed posture, like the
operator and comms states: it gates which comms links may emit, independent of
physical link health, so the audit can tell "the operator silenced us" from "the
link is physically dead". A named emission profile lists the links permitted to
transmit; the device emits on a link only when the active profile permits it.

Two profiles are always available: ``unrestricted`` (every configured link) and
``silent`` (no link, full radio silence). Further named profiles come from an
optional ``comms.emcon`` profile section, so a profile without one leaves EMCON
unrestricted and inert, exactly as before.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["SILENT", "UNRESTRICTED", "Emcon"]

UNRESTRICTED = "unrestricted"
SILENT = "silent"


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
        default = UNRESTRICTED
        if isinstance(section, Mapping):
            raw_profiles = section.get("profiles")
            if isinstance(raw_profiles, Mapping):
                for name, body in raw_profiles.items():
                    if isinstance(name, str) and name.strip():
                        self._profiles[name.strip()] = _parse_links(body, all_links)
            raw_default = section.get("default")
            if isinstance(raw_default, str) and raw_default.strip() in self._profiles:
                default = raw_default.strip()
        self._active = default

    def permits(self, link_id: str) -> bool:
        """Whether the active profile lets the device emit on ``link_id``."""
        return link_id in self._profiles.get(self._active, self._all)

    @property
    def active(self) -> str:
        return self._active

    def set_profile(self, name: str) -> bool:
        """Activate a named profile. False (and no change) if it is unknown."""
        if name in self._profiles:
            self._active = name
            return True
        return False

    def status(self) -> dict[str, Any]:
        """The read surface for the ``emcon_status`` tool."""
        return {
            "active": self._active,
            "configured": self.configured,
            "permitted_links": sorted(self._profiles.get(self._active, self._all)),
            "profiles": {
                name: sorted(links) for name, links in sorted(self._profiles.items())
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
    if isinstance(raw, str):
        low = raw.strip().lower()
        if low in ("all", "*"):
            return set(all_links)
        if low in ("none", ""):
            return set()
        return {raw.strip()}
    if isinstance(raw, (list, tuple)):
        return {x.strip() for x in raw if isinstance(x, str) and x.strip()}
    return set()
