"""PMU/PDU: bus regulation, CC/CV charging, dual-slot battery hot-swap (BL-005b).

ADR-0015 made the primary Li-ion pack the sole bus and let the power subsystem
clamp the APU charge to its own ``charge_limit_w``. BL-005b lifts that bus
regulation onto a power-management unit and adds the posture ADR-0015 deferred (its
own revisit trigger): a dual battery slot where the inactive pack can be removed
without collapsing the bus, and the PMU arbitrates which slot powers the load.

The PMU sits between the APU and the battery slots. Each tick the engine asks it to
regulate the APU's offered power into the accepted charge (the ``charge_limit``
clamp plus a CC/CV taper that backs the current off as the active pack approaches
full), the engine routes the load and that charge to the active pack, and the PMU
arbitrates: when the active pack is exhausted it switches to a charged standby slot,
keeping the device alive across a pack swap. The standby slot can be removed
(:meth:`remove_slot`) and a fresh pack inserted (:meth:`insert_slot`) without
interrupting the active bus.

Profile fields live under ``pmu``: ``charge_limit_w`` (defaults to the legacy
``power.charge_limit_w`` so existing profiles keep their bus limit), ``cv_soc_pct``
(the CC/CV knee), ``cv_floor_frac`` (the taper floor near full), and an optional
``secondary`` mapping (a second pack; inherits the ``power`` config, overridable)
that enables the dual-slot posture.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

import numpy as np

from .power import PowerSubsystem

__all__ = ["ChargeMode", "PmuSubsystem", "Slot"]

_DEFAULT_CHARGE_LIMIT_W = 100.0
_DEFAULT_CV_SOC_PCT = 80.0
_DEFAULT_CV_FLOOR_FRAC = 0.05


class Slot(StrEnum):
    """The two battery slots the PMU arbitrates."""

    PRIMARY = "primary"
    SECONDARY = "secondary"


class ChargeMode(StrEnum):
    """The CC/CV charge stage the PMU is in this tick."""

    IDLE = "idle"
    CONSTANT_CURRENT = "cc"
    CONSTANT_VOLTAGE = "cv"


class PmuSubsystem:
    """Power-management unit: bus regulation + dual-slot battery arbitration."""

    name: str = "pmu"

    def __init__(
        self,
        primary: PowerSubsystem,
        *,
        secondary: PowerSubsystem | None = None,
        profile: Mapping[str, Any],
    ) -> None:
        cfg = dict(profile.get("pmu") or {})
        power_cfg = dict(profile.get("power") or {})
        fallback_limit = float(power_cfg.get("charge_limit_w", _DEFAULT_CHARGE_LIMIT_W))
        self._charge_limit_w = max(0.0, float(cfg.get("charge_limit_w", fallback_limit)))
        self._cv_soc_pct = _clamp_pct(float(cfg.get("cv_soc_pct", _DEFAULT_CV_SOC_PCT)))
        self._cv_floor_frac = max(
            0.0, min(1.0, float(cfg.get("cv_floor_frac", _DEFAULT_CV_FLOOR_FRAC)))
        )
        self._slots: dict[Slot, PowerSubsystem | None] = {
            Slot.PRIMARY: primary,
            Slot.SECONDARY: secondary,
        }
        self._active = Slot.PRIMARY
        self._charge_offered_w = 0.0
        self._charge_accepted_w = 0.0
        self._mode = ChargeMode.IDLE
        self._swaps = 0
        self._t = 0.0

    @classmethod
    def from_profile(
        cls, profile: Mapping[str, Any], *, rng: np.random.Generator | None = None
    ) -> PmuSubsystem:
        """Build the PMU with a primary pack and an optional secondary from the profile."""
        primary = PowerSubsystem(profile, rng=rng)
        secondary = _build_secondary(profile, rng)
        return cls(primary, secondary=secondary, profile=profile)

    @property
    def active_battery(self) -> PowerSubsystem:
        battery = self._slots[self._active]
        if battery is None:
            # Invariant: the active slot always holds a pack (remove_slot refuses
            # the active slot, and arbitration only ever activates a present one).
            raise RuntimeError("PMU active slot is empty")
        return battery

    @property
    def active_slot(self) -> Slot:
        return self._active

    @property
    def charge_offered_w(self) -> float:
        return self._charge_offered_w

    @property
    def charge_accepted_w(self) -> float:
        return self._charge_accepted_w

    def slot_present(self, slot: Slot) -> bool:
        return self._slots[slot] is not None

    def regulate_charge(self, offered_w: float) -> float:
        """Clamp + CC/CV taper the offered source power into the accepted charge.

        Below the ``cv_soc_pct`` knee the limit is the full ``charge_limit_w``
        (constant current); above it the limit tapers linearly to
        ``cv_floor_frac`` of the limit at full charge (constant voltage), the
        standard Li-ion charge profile. The accepted charge is the lesser of the
        offered power and that limit; the offered value is recorded so a
        controller sees how much source power the bus clipped.
        """
        offered = max(0.0, float(offered_w))
        self._charge_offered_w = offered
        soc = self.active_battery.soc_pct
        if soc < self._cv_soc_pct:
            cap = self._charge_limit_w
            mode = ChargeMode.CONSTANT_CURRENT
        else:
            span = max(1e-6, 100.0 - self._cv_soc_pct)
            frac = max(0.0, (100.0 - soc) / span)  # 1 at the knee, 0 at full
            cap = self._charge_limit_w * (
                self._cv_floor_frac + (1.0 - self._cv_floor_frac) * frac
            )
            mode = ChargeMode.CONSTANT_VOLTAGE
        accepted = min(offered, max(0.0, cap))
        self._mode = ChargeMode.IDLE if offered <= 0.0 else mode
        self._charge_accepted_w = accepted
        return accepted

    def arbitrate(self) -> bool:
        """Switch to a charged standby slot if the active pack is exhausted.

        Returns ``True`` if a swap happened. Handing the bus to a charged standby
        keeps the device alive across a depleted active pack, with no bus collapse.
        """
        if self.active_battery.soc_pct > 0.0:
            return False
        other = Slot.SECONDARY if self._active is Slot.PRIMARY else Slot.PRIMARY
        standby = self._slots[other]
        if standby is not None and standby.soc_pct > 0.0:
            self._active = other
            self._swaps += 1
            return True
        return False

    def remove_slot(self, slot: Slot) -> bool:
        """Remove the pack in ``slot``; refuses the active slot (would collapse the bus)."""
        if slot is self._active or self._slots[slot] is None:
            return False
        self._slots[slot] = None
        return True

    def insert_slot(self, slot: Slot, battery: PowerSubsystem) -> bool:
        """Insert a fresh pack into an empty ``slot``; refuses an occupied slot."""
        if self._slots[slot] is not None:
            return False
        self._slots[slot] = battery
        return True

    def switch_active(self, slot: Slot) -> bool:
        """Make ``slot`` the active bus; refuses an empty slot."""
        if self._slots[slot] is None:
            return False
        if slot is not self._active:
            self._active = slot
            self._swaps += 1
        return True

    def step(self, dt: float) -> None:
        if dt > 0.0:
            self._t += dt

    def truth(self) -> Mapping[str, Any]:
        secondary = self._slots[Slot.SECONDARY]
        return {
            "charge_limit_w": self._charge_limit_w,
            "charge_offered_w": self._charge_offered_w,
            "charge_accepted_w": self._charge_accepted_w,
            "charge_mode": str(self._mode),
            "active_slot": str(self._active),
            "primary_present": self.slot_present(Slot.PRIMARY),
            "secondary_present": secondary is not None,
            "secondary_soc_pct": secondary.soc_pct if secondary is not None else None,
            "swaps": self._swaps,
            "t": self._t,
        }


def _build_secondary(
    profile: Mapping[str, Any], rng: np.random.Generator | None
) -> PowerSubsystem | None:
    cfg = dict(profile.get("pmu") or {})
    secondary = cfg.get("secondary")
    if not isinstance(secondary, Mapping) or secondary.get("enabled") is False:
        return None
    power_cfg = dict(profile.get("power") or {})
    overrides = {k: v for k, v in secondary.items() if k != "enabled"}
    sub_profile = {"power": {**power_cfg, **overrides}}
    return PowerSubsystem(sub_profile, rng=rng)


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))
