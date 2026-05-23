"""Two-state thermal model: junction + enclosure (BL-005).

Implements the :class:`~nous.subsystems.base.Subsystem` Protocol. The
model captures the dominant thermal path on a passively-cooled backpack
appliance:

* heat is generated at the **junction** (compute die, AI accelerator),
* flows through a junction-to-enclosure thermal resistance into the
  **enclosure** (heatspreader, case, internal air),
* and dissipates from the enclosure to **ambient** through a second
  resistance (natural convection + radiation).

Two state variables (``junction_c``, ``enclosure_c``) integrate the
lumped-capacitance equations forward in time; ``ambient_c`` is an
exogenous input the engine drives from the profile default or a
scenario injector. The junction time constant is short (seconds), the
enclosure time constant is long (minutes), so the model exhibits the
characteristic "quick spike then slow soak" of a real package.

Parameters come from the hardware profile (`thermal.*`). The two new
optional fields land with sensible defaults so older profiles continue
to load:

* ``junction_heat_capacity_j_per_k`` -- junction thermal mass
  (default ``5.0`` J/K, roughly a Jetson-class die).
* ``enclosure_to_ambient_resistance_c_per_w`` -- enclosure-to-ambient
  thermal resistance (default ``0.5`` C/W, natural-convection range
  for a fanless 1-kg enclosure).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["ThermalSubsystem"]


_DEFAULT_AMBIENT_C = 25.0
_DEFAULT_JUNCTION_TEMP_MAX = 95.0
_DEFAULT_JUNCTION_TEMP_THROTTLE = 85.0
_DEFAULT_R_JUNCTION_TO_ENCLOSURE = 0.30
_DEFAULT_R_ENCLOSURE_TO_AMBIENT = 0.5
_DEFAULT_ENCLOSURE_MASS_KG = 1.2
_DEFAULT_ENCLOSURE_SPECIFIC_HEAT = 900.0
_DEFAULT_JUNCTION_HEAT_CAPACITY = 5.0
_DEFAULT_HEADROOM_THRESHOLD_C = 5.0


class ThermalSubsystem:
    """Two-state lumped thermal model coupling compute load to junction temp.

    State variables:

    * ``junction_c`` -- die temperature (fast time constant).
    * ``enclosure_c`` -- enclosure / heatspreader temperature (slow).

    Dynamics (forward Euler):

    ``C_j * dT_j/dt = P_load - (T_j - T_e) / R_je``
    ``C_e * dT_e/dt = (T_j - T_e) / R_je - (T_e - T_amb) / R_ea``

    where:

    * ``P_load`` -- heat dissipated at the junction (W), set per tick
      from the compute load.
    * ``R_je`` -- junction-to-enclosure thermal resistance (C/W) from
      ``thermal.thermal_resistance_c_per_w``.
    * ``R_ea`` -- enclosure-to-ambient thermal resistance (C/W) from
      ``thermal.enclosure_to_ambient_resistance_c_per_w``.
    * ``C_e`` -- enclosure thermal capacitance (J/K), computed from
      ``enclosure_mass_kg * enclosure_specific_heat_j_per_kg_k``.
    * ``C_j`` -- junction thermal capacitance (J/K) from
      ``thermal.junction_heat_capacity_j_per_k``.

    Compute load and ambient are external inputs: :meth:`set_load_w`
    records the dissipation; :meth:`set_ambient_c` records the
    operator-environment temperature. The engine calls both each tick
    before :meth:`step`.
    """

    name: str = "thermal"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        cfg = dict(profile.get("thermal") or {})
        self._ambient_default_c = float(
            cfg.get("ambient_c_default", _DEFAULT_AMBIENT_C)
        )
        self._junction_temp_max = float(
            cfg.get("junction_temp_max", _DEFAULT_JUNCTION_TEMP_MAX)
        )
        self._junction_temp_throttle = float(
            cfg.get("junction_temp_throttle", _DEFAULT_JUNCTION_TEMP_THROTTLE)
        )
        self._r_je = max(
            1e-3,
            float(cfg.get("thermal_resistance_c_per_w", _DEFAULT_R_JUNCTION_TO_ENCLOSURE)),
        )
        self._r_ea = max(
            1e-3,
            float(
                cfg.get(
                    "enclosure_to_ambient_resistance_c_per_w",
                    _DEFAULT_R_ENCLOSURE_TO_AMBIENT,
                )
            ),
        )
        mass = float(cfg.get("enclosure_mass_kg", _DEFAULT_ENCLOSURE_MASS_KG))
        cp = float(
            cfg.get(
                "enclosure_specific_heat_j_per_kg_k",
                _DEFAULT_ENCLOSURE_SPECIFIC_HEAT,
            )
        )
        self._c_e = max(1.0, mass * cp)
        self._c_j = max(
            0.1,
            float(
                cfg.get("junction_heat_capacity_j_per_k", _DEFAULT_JUNCTION_HEAT_CAPACITY)
            ),
        )
        self._headroom_threshold_c = float(
            cfg.get("headroom_threshold_c", _DEFAULT_HEADROOM_THRESHOLD_C)
        )

        self._load_w = 0.0
        self._ambient_c = self._ambient_default_c
        self._enclosure_c = self._ambient_default_c
        self._junction_c = self._ambient_default_c
        self._t = 0.0

    def set_load_w(self, load_w: float) -> None:
        """Record the heat dissipated at the junction this tick (W)."""
        self._load_w = max(0.0, float(load_w))

    def set_ambient_c(self, ambient_c: float) -> None:
        """Update the ambient temperature input (C)."""
        self._ambient_c = float(ambient_c)

    @property
    def junction_c(self) -> float:
        return self._junction_c

    @property
    def enclosure_c(self) -> float:
        return self._enclosure_c

    @property
    def ambient_c(self) -> float:
        return self._ambient_c

    @property
    def load_w(self) -> float:
        return self._load_w

    @property
    def junction_temp_throttle(self) -> float:
        return self._junction_temp_throttle

    @property
    def junction_temp_max(self) -> float:
        return self._junction_temp_max

    @property
    def headroom_threshold_c(self) -> float:
        return self._headroom_threshold_c

    @property
    def headroom_c(self) -> float:
        """Headroom to the throttle threshold (positive == cool)."""
        return self._junction_temp_throttle - self._junction_c

    @property
    def throttling(self) -> bool:
        return self._junction_c >= self._junction_temp_throttle

    def set_junction_c(self, junction_c: float) -> None:
        """Force the junction temperature (test and scenario seed helper)."""
        self._junction_c = float(junction_c)

    def set_enclosure_c(self, enclosure_c: float) -> None:
        """Force the enclosure temperature (test and scenario seed helper)."""
        self._enclosure_c = float(enclosure_c)

    def step(self, dt: float) -> None:
        """Advance one tick with forward Euler integration."""
        if dt <= 0.0:
            return
        self._t += dt
        q_je = (self._junction_c - self._enclosure_c) / self._r_je
        q_ea = (self._enclosure_c - self._ambient_c) / self._r_ea
        dtj = (self._load_w - q_je) / self._c_j
        dte = (q_je - q_ea) / self._c_e
        self._junction_c = self._junction_c + dtj * dt
        self._enclosure_c = self._enclosure_c + dte * dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "junction_c": self._junction_c,
            "enclosure_c": self._enclosure_c,
            "ambient_c": self._ambient_c,
            "load_w": self._load_w,
            "headroom_c": self.headroom_c,
            "throttling": self.throttling,
            "junction_temp_throttle": self._junction_temp_throttle,
            "junction_temp_max": self._junction_temp_max,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "junction_c": self._junction_c,
                "enclosure_c": self._enclosure_c,
                "ambient_c": self._ambient_c,
            },
            noise={
                "junction_c_sigma": 1.0,
                "enclosure_c_sigma": 0.5,
                "ambient_c_sigma": 0.5,
            },
        )
