"""Auxiliary power unit: solar PV + methanol fuel cell + vehicle + USB-C PD.

Implements the :class:`~nous.subsystems.base.Subsystem` Protocol. The APU
composes four auxiliary sources into a single total power offered to the
battery; the bus regulator on
:meth:`~nous.subsystems.power.PowerSubsystem.set_charge_w` clamps that to
the battery's charge-acceptance budget. The APU is strictly auxiliary
(ADR-0015): every watt it produces flows through the primary Li-ion pack,
never directly to compute.

Per-source physics:

* **Solar PV with MPPT.** MPPT efficiency multiplies the incident
  irradiance; output is then derated by panel temperature above 25 C
  and clipped to ``panel_w_peak``.
* **Methanol fuel cell.** Output tracks a 0..1 load fraction (or a
  scenario override). Fuel mass depletes at
  ``output_w * dt / wh_per_g_fuel``; if ``wh_per_g_fuel`` is omitted
  the model derives it from ``efficiency * methanol_lhv_wh_per_g``.
  When the tank empties, output is forced to zero.
* **Vehicle tether.** Connected/disconnected, with the bus's offered
  power clamped to ``bus_voltage_v * current_limit_a``.
* **USB-C PD-in.** Discrete PD profiles (W). The negotiated value is
  the largest available profile less than or equal to the
  controller's request; the construction-time
  ``default_profile_w`` is run through the same negotiation so a YAML
  default outside the advertised profiles cannot leak a non-PD power
  level.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["ApuSubsystem"]


_DEFAULT_PANEL_W_PEAK = 0.0
_DEFAULT_MPPT_EFFICIENCY = 0.92
_DEFAULT_PANEL_TEMP_DERATE_PER_C = 0.004
_DEFAULT_FUELCELL_CONTINUOUS_W = 0.0
_DEFAULT_FUEL_CAPACITY_G = 0.0
_DEFAULT_FUELCELL_EFFICIENCY = 0.0
_DEFAULT_WH_PER_G_FUEL = 2.5
_DEFAULT_VEHICLE_BUS_V = 12.0
_DEFAULT_VEHICLE_CURRENT_LIMIT_A = 0.0
_DEFAULT_USBC_DEFAULT_W = 0.0
_DEFAULT_PANEL_TEMP_C = 25.0
_METHANOL_LHV_WH_PER_G = 5.53


def _coalesce_float(*candidates: Any, default: float) -> float:
    """First non-None candidate cast to ``float``; ``default`` if all are None."""
    for value in candidates:
        if value is not None:
            return float(value)
    return float(default)


class ApuSubsystem:
    """Four-source auxiliary power unit (BL-005a).

    Each tick, the engine reads :attr:`total_w` and feeds it to the power
    subsystem as charge inflow. Sources can be steered either from the
    raw input side (``set_solar_insolation_w``, ``set_fuelcell_load_pct``)
    or via direct power overrides (``set_solar_w``, ``set_fuelcell_w``)
    that match the existing scenario YAML vocabulary.
    """

    name: str = "apu"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        apu_cfg = dict(profile.get("apu") or {})

        solar_cfg = dict(apu_cfg.get("solar") or {})
        self._solar_w_peak = _coalesce_float(
            solar_cfg.get("panel_w_peak"),
            apu_cfg.get("solar_w_peak"),
            default=_DEFAULT_PANEL_W_PEAK,
        )
        self._mppt_efficiency = _coalesce_float(
            solar_cfg.get("mppt_efficiency"), default=_DEFAULT_MPPT_EFFICIENCY
        )
        self._panel_temp_derate_per_c = _coalesce_float(
            solar_cfg.get("panel_temp_derate_per_c_above_25"),
            default=_DEFAULT_PANEL_TEMP_DERATE_PER_C,
        )

        fc_cfg = dict(apu_cfg.get("fuel_cell") or {})
        self._fuelcell_continuous_w = _coalesce_float(
            fc_cfg.get("continuous_w"),
            apu_cfg.get("fuelcell_w_continuous"),
            default=_DEFAULT_FUELCELL_CONTINUOUS_W,
        )
        self._fuel_capacity_g = _coalesce_float(
            fc_cfg.get("fuel_capacity_g"),
            apu_cfg.get("fuelcell_fuel_capacity_g"),
            default=_DEFAULT_FUEL_CAPACITY_G,
        )
        self._fuelcell_efficiency = _coalesce_float(
            fc_cfg.get("efficiency"),
            apu_cfg.get("fuelcell_efficiency"),
            default=_DEFAULT_FUELCELL_EFFICIENCY,
        )
        explicit_wh_per_g = fc_cfg.get("wh_per_g_fuel")
        if explicit_wh_per_g is not None:
            self._wh_per_g_fuel = float(explicit_wh_per_g)
        elif self._fuelcell_efficiency > 0.0:
            self._wh_per_g_fuel = (
                self._fuelcell_efficiency * _METHANOL_LHV_WH_PER_G
            )
        else:
            self._wh_per_g_fuel = _DEFAULT_WH_PER_G_FUEL

        veh_cfg = dict(apu_cfg.get("vehicle") or {})
        self._vehicle_bus_v = _coalesce_float(
            veh_cfg.get("bus_voltage_v"), default=_DEFAULT_VEHICLE_BUS_V
        )
        self._vehicle_current_limit_a = _coalesce_float(
            veh_cfg.get("current_limit_a"), default=_DEFAULT_VEHICLE_CURRENT_LIMIT_A
        )

        usbc_cfg = dict(apu_cfg.get("usb_c_pd") or {})
        raw_profiles = usbc_cfg.get("profiles_w") or []
        self._usbc_profiles_w: tuple[float, ...] = tuple(
            sorted(
                float(w)
                for w in raw_profiles
                if isinstance(w, (int, float)) and float(w) > 0.0
            )
        )
        configured_default_w = _coalesce_float(
            usbc_cfg.get("default_profile_w"), default=_DEFAULT_USBC_DEFAULT_W
        )
        self._usbc_default_w = self._pick_usbc_profile(configured_default_w)

        self._solar_insolation_w: float | None = None
        self._panel_temp_c = _DEFAULT_PANEL_TEMP_C
        self._solar_w_override: float | None = None
        self._fuelcell_load_pct = 0.0
        self._fuelcell_w_override: float | None = None
        self._vehicle_connected = False
        self._vehicle_offered_w = 0.0
        self._usbc_connected = False
        self._usbc_profile_w = self._usbc_default_w

        self._t = 0.0
        self._fuel_g = self._fuel_capacity_g
        self._solar_w = 0.0
        self._fuelcell_w = 0.0
        self._vehicle_w = 0.0
        self._usbc_w = 0.0

    def set_solar_w(self, watts: float) -> None:
        """Override the next tick's solar output directly (scenario shortcut)."""
        self._solar_w_override = max(0.0, float(watts))

    def set_solar_insolation_w(
        self, watts: float, panel_temp_c: float | None = None
    ) -> None:
        """Set the irradiance presented to the panel and derive MPPT output."""
        self._solar_insolation_w = max(0.0, float(watts))
        if panel_temp_c is not None:
            self._panel_temp_c = float(panel_temp_c)
        self._solar_w_override = None

    def set_fuelcell_w(self, watts: float) -> None:
        """Override the next tick's fuel-cell output (scenario shortcut)."""
        self._fuelcell_w_override = max(0.0, float(watts))

    def set_fuelcell_load_pct(self, pct: float) -> None:
        """Set the fuel-cell load fraction in [0, 1]; derives output and fuel burn."""
        self._fuelcell_load_pct = max(0.0, min(1.0, float(pct)))
        self._fuelcell_w_override = None

    def set_vehicle(self, connected: bool, offered_w: float = 0.0) -> None:
        """Vehicle tether: connection flag plus the bus's offered power (W)."""
        self._vehicle_connected = bool(connected)
        self._vehicle_offered_w = max(0.0, float(offered_w))

    def set_usb_c_pd(self, connected: bool, profile_w: float | None = None) -> None:
        """USB-C PD: connection flag plus the negotiated profile (W)."""
        self._usbc_connected = bool(connected)
        if profile_w is not None:
            self._usbc_profile_w = self._pick_usbc_profile(profile_w)

    def refuel(self, grams: float) -> None:
        """Add fuel (g) to the methanol cell, clamped to ``fuel_capacity_g``."""
        self._fuel_g = max(
            0.0, min(self._fuel_capacity_g, self._fuel_g + float(grams))
        )

    @property
    def total_w(self) -> float:
        """Total auxiliary power the APU is currently producing."""
        return self._solar_w + self._fuelcell_w + self._vehicle_w + self._usbc_w

    @property
    def fuel_pct(self) -> float:
        if self._fuel_capacity_g <= 0.0:
            return 0.0
        return 100.0 * self._fuel_g / self._fuel_capacity_g

    @property
    def usbc_profiles_w(self) -> tuple[float, ...]:
        return self._usbc_profiles_w

    def step(self, dt: float) -> None:
        if dt < 0.0:
            return
        self._t += max(0.0, dt)
        self._solar_w = self._compute_solar_w()
        self._fuelcell_w = self._compute_fuelcell_w(dt)
        self._vehicle_w = self._compute_vehicle_w()
        self._usbc_w = self._compute_usbc_w()

    def truth(self) -> Mapping[str, Any]:
        return {
            "solar_w": self._solar_w,
            "fuelcell_w": self._fuelcell_w,
            "vehicle_w": self._vehicle_w,
            "usbc_w": self._usbc_w,
            "total_w": self.total_w,
            "fuel_g": self._fuel_g,
            "fuel_pct": self.fuel_pct,
            "vehicle_connected": self._vehicle_connected,
            "usbc_connected": self._usbc_connected,
            "usbc_profile_w": self._usbc_profile_w if self._usbc_connected else 0.0,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "solar_w": self._solar_w,
                "fuelcell_w": self._fuelcell_w,
                "vehicle_w": self._vehicle_w,
                "usbc_w": self._usbc_w,
                "total_w": self.total_w,
            },
            noise={
                "solar_w_sigma": 1.0,
                "fuelcell_w_sigma": 0.5,
                "vehicle_w_sigma": 0.5,
                "usbc_w_sigma": 0.2,
                "total_w_sigma": 2.0,
            },
        )

    def _compute_solar_w(self) -> float:
        if self._solar_w_override is not None:
            return max(0.0, min(self._solar_w_peak, self._solar_w_override))
        if self._solar_w_peak <= 0.0 or self._solar_insolation_w is None:
            return 0.0
        derate = 1.0 - self._panel_temp_derate_per_c * max(
            0.0, self._panel_temp_c - 25.0
        )
        derate = max(0.0, derate)
        raw = self._mppt_efficiency * self._solar_insolation_w * derate
        return max(0.0, min(self._solar_w_peak, raw))

    def _compute_fuelcell_w(self, dt: float) -> float:
        if self._fuel_g <= 0.0 or self._fuelcell_continuous_w <= 0.0:
            return 0.0
        if self._fuelcell_w_override is not None:
            out = min(self._fuelcell_continuous_w, self._fuelcell_w_override)
        else:
            out = self._fuelcell_continuous_w * self._fuelcell_load_pct
        if out <= 0.0 or dt <= 0.0:
            return max(0.0, out)
        wh_per_g = max(self._wh_per_g_fuel, 1e-3)
        burn_g = out * (dt / 3600.0) / wh_per_g
        if burn_g >= self._fuel_g:
            burn_g = self._fuel_g
            out = burn_g * wh_per_g / (dt / 3600.0)
        self._fuel_g = max(0.0, self._fuel_g - burn_g)
        return max(0.0, out)

    def _compute_vehicle_w(self) -> float:
        if not self._vehicle_connected:
            return 0.0
        cap = self._vehicle_bus_v * self._vehicle_current_limit_a
        if cap <= 0.0:
            return 0.0
        return min(self._vehicle_offered_w, cap)

    def _compute_usbc_w(self) -> float:
        if not self._usbc_connected:
            return 0.0
        return self._usbc_profile_w

    def _pick_usbc_profile(self, requested_w: float) -> float:
        requested = max(0.0, float(requested_w))
        if requested <= 0.0:
            return 0.0
        if not self._usbc_profiles_w:
            return requested
        eligible = [w for w in self._usbc_profiles_w if w <= requested]
        if eligible:
            return max(eligible)
        return min(self._usbc_profiles_w)
