"""Primary battery model: Li-ion with Peukert correction and thermal derate.

Implements the :class:`~nous.subsystems.base.Subsystem` Protocol. The model
is a single Li-ion pack whose discharge curves come from the hardware
profile (``battery_wh``, ``voltage_v_nominal``, ``peukert_k``,
``internal_resistance_ohm``, ``thermal_derate_c``, ...). Charge input
arrives from the PMU (see :mod:`nous.subsystems.pmu`), which owns the bus
regulation (the ``charge_limit_w`` clamp and the CC/CV taper, BL-005b /
ADR 0075); the battery records the already-regulated charge it is handed.

The battery is the *primary* power source. APU sources are auxiliary and
never deliver power directly to the load (see ADR-0015). Per
``LIMITATIONS.md`` L8 the model is Li-ion only; alternative chemistries
(LiFePO4, solid state) are tracked under BL-042.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

import numpy as np

from ..types import Observation

__all__ = ["PowerFlag", "PowerSubsystem"]


_DEFAULT_BATTERY_WH = 100.0
_DEFAULT_VOLTAGE_NOMINAL = 14.4
_DEFAULT_VOLTAGE_MIN = 12.0
_DEFAULT_VOLTAGE_MAX = 16.8
_DEFAULT_INTERNAL_RESISTANCE_OHM = 0.05
_DEFAULT_RATED_CURRENT_A = 5.0
_DEFAULT_PEUKERT_K = 1.04
_DEFAULT_LOW_THRESHOLD = 20.0
_DEFAULT_CRITICAL_THRESHOLD = 5.0
_DEFAULT_THERMAL_DERATE_C = 45.0
_DEFAULT_DERATE_SLOPE_PER_C = 0.02
_DEFAULT_INITIAL_SOC_PCT = 100.0
_DEFAULT_CELL_C = 25.0


class PowerFlag(StrEnum):
    """Coarse SoC flag the controller surfaces to the operator."""

    NOMINAL = "nominal"
    LOW = "low"
    CRITICAL = "critical"
    EMPTY = "empty"
    FULL = "full"


class PowerSubsystem:
    """Li-ion battery with Peukert correction and thermal derate (BL-003).

    The simulator integrates state-of-charge with coulomb counting against
    the *effective* capacity at the present current and cell temperature.
    Terminal voltage tracks an open-circuit linear curve from
    ``voltage_v_min`` (at 0% SoC) to ``voltage_v_max`` (at 100%) minus the
    ohmic drop ``I * internal_resistance_ohm``.

    Load and charge inputs are external: :meth:`set_load_w` records the
    aggregate compute and accessory draw, :meth:`set_charge_w` records the
    APU's contribution. The engine calls both each tick before
    :meth:`step`.
    """

    name: str = "power"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.profile = profile
        # ADR 0019 follow-up: every subsystem now accepts the engine's
        # ``rng`` so future noise-sampling work can draw from a
        # deterministic seam without reaching for the ``numpy.random``
        # global. Today's subsystems do not sample; the kwarg is
        # stored for the next contributor.
        self._rng = rng
        cfg = dict(profile.get("power") or {})
        self._battery_wh = float(cfg.get("battery_wh", _DEFAULT_BATTERY_WH))
        self._voltage_nominal = float(
            cfg.get("voltage_v_nominal", _DEFAULT_VOLTAGE_NOMINAL)
        )
        self._voltage_min = float(cfg.get("voltage_v_min", _DEFAULT_VOLTAGE_MIN))
        self._voltage_max = float(cfg.get("voltage_v_max", _DEFAULT_VOLTAGE_MAX))
        self._internal_resistance_ohm = float(
            cfg.get("internal_resistance_ohm", _DEFAULT_INTERNAL_RESISTANCE_OHM)
        )
        self._rated_current_a = float(
            cfg.get("rated_current_a", _DEFAULT_RATED_CURRENT_A)
        )
        self._peukert_k = float(cfg.get("peukert_k", _DEFAULT_PEUKERT_K))
        self._low_threshold = float(
            cfg.get("soc_pct_low_threshold", _DEFAULT_LOW_THRESHOLD)
        )
        self._critical_threshold = float(
            cfg.get("soc_pct_critical_threshold", _DEFAULT_CRITICAL_THRESHOLD)
        )
        self._thermal_derate_c = float(
            cfg.get("thermal_derate_c", _DEFAULT_THERMAL_DERATE_C)
        )
        self._derate_slope_per_c = float(
            cfg.get("thermal_derate_slope_per_c", _DEFAULT_DERATE_SLOPE_PER_C)
        )
        self._nominal_capacity_ah = self._battery_wh / max(self._voltage_nominal, 1.0)

        self._load_w = 0.0
        self._charge_offered_w = 0.0
        self._charge_accepted_w = 0.0
        self._cell_c = _DEFAULT_CELL_C

        self._t = 0.0
        self._soc_pct = _DEFAULT_INITIAL_SOC_PCT
        self._current_a = 0.0
        self._voltage_v = self._open_circuit_voltage(self._soc_pct)

    def set_load_w(self, load_w: float) -> None:
        """Record the aggregate load drawn from the battery this tick."""
        self._load_w = max(0.0, float(load_w))

    def set_charge_w(self, charge_w: float) -> None:
        """Record the charge delivered to the battery this tick.

        The bus regulation (the ``charge_limit_w`` clamp and the CC/CV taper)
        moved to the PMU (BL-005b / ADR 0075): the value passed here is already
        the regulated, accepted charge, so the battery records it as both the
        offered and accepted figure. The PMU surfaces how much source power was
        clipped.
        """
        accepted = max(0.0, float(charge_w))
        self._charge_offered_w = accepted
        self._charge_accepted_w = accepted

    def set_cell_c(self, cell_c: float) -> None:
        """Update the cell temperature used for the thermal derate."""
        self._cell_c = float(cell_c)

    def set_soc_pct(self, soc_pct: float) -> None:
        """Force a SoC (test and scenario seed helper). Clamps to [0, 100]."""
        self._soc_pct = max(0.0, min(100.0, float(soc_pct)))
        self._voltage_v = self._open_circuit_voltage(self._soc_pct)

    @property
    def soc_pct(self) -> float:
        return self._soc_pct

    @property
    def voltage_v(self) -> float:
        return self._voltage_v

    @property
    def current_a(self) -> float:
        return self._current_a

    @property
    def remaining_wh(self) -> float:
        return self._battery_wh * (self._soc_pct / 100.0)

    @property
    def flag(self) -> PowerFlag:
        if self._soc_pct <= 0.0:
            return PowerFlag.EMPTY
        if self._soc_pct >= 100.0:
            return PowerFlag.FULL
        if self._soc_pct < self._critical_threshold:
            return PowerFlag.CRITICAL
        if self._soc_pct < self._low_threshold:
            return PowerFlag.LOW
        return PowerFlag.NOMINAL

    @property
    def endurance_min(self) -> float | None:
        """Minutes of endurance at the current net load (None if charging)."""
        net_w = self._load_w - self._charge_accepted_w
        if net_w <= 0.0:
            return None
        if self._soc_pct <= 0.0:
            return 0.0
        return (self.remaining_wh / net_w) * 60.0

    def step(self, dt: float) -> None:
        """Advance one tick.

        Walks one fixed-point iteration of (V_terminal, I) at the previous
        SoC, integrates SoC against the effective capacity for ``dt``
        seconds, then refreshes the reported terminal voltage and current.
        """
        if dt <= 0.0:
            return
        self._t += dt

        v_ocv = self._open_circuit_voltage(self._soc_pct)
        v_terminal = max(
            self._voltage_min,
            v_ocv - self._internal_resistance_ohm * self._current_a,
        )

        load_a = self._load_w / max(v_terminal, 1.0)
        charge_a = self._charge_accepted_w / max(v_terminal, 1.0)
        net_a = load_a - charge_a
        discharging = net_a > 0.0

        c_eff_ah = self._effective_capacity_ah(abs(net_a), discharging=discharging)
        dsoc = -100.0 * net_a * (dt / 3600.0) / c_eff_ah
        soc_new = self._soc_pct + dsoc
        if soc_new < 0.0:
            soc_new = 0.0
            net_a = 0.0
        elif soc_new > 100.0:
            soc_new = 100.0
            net_a = 0.0
        self._soc_pct = soc_new
        self._current_a = net_a

        v_terminal_new = self._open_circuit_voltage(self._soc_pct) - (
            self._internal_resistance_ohm * net_a
        )
        self._voltage_v = max(
            self._voltage_min, min(self._voltage_max, v_terminal_new)
        )

    def truth(self) -> Mapping[str, Any]:
        return {
            "soc_pct": self._soc_pct,
            "voltage_v": self._voltage_v,
            "current_a": self._current_a,
            "cell_c": self._cell_c,
            "load_w": self._load_w,
            "charge_offered_w": self._charge_offered_w,
            "charge_accepted_w": self._charge_accepted_w,
            "remaining_wh": self.remaining_wh,
            "endurance_min": self.endurance_min,
            "flag": str(self.flag),
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "soc_pct": self._soc_pct,
                "voltage_v": self._voltage_v,
                "current_a": self._current_a,
                "load_w": self._load_w,
            },
            noise={
                "soc_pct_sigma": 0.5,
                "voltage_v_sigma": 0.05,
                "current_a_sigma": 0.10,
                "load_w_sigma": 0.25,
            },
        )

    def _open_circuit_voltage(self, soc_pct: float) -> float:
        soc = max(0.0, min(100.0, soc_pct))
        return self._voltage_min + (self._voltage_max - self._voltage_min) * (
            soc / 100.0
        )

    def _effective_capacity_ah(
        self, current_a: float, *, discharging: bool = True
    ) -> float:
        c = self._nominal_capacity_ah
        i = max(current_a, 1e-3)
        if discharging and i > self._rated_current_a and self._peukert_k > 1.0:
            c = c * (self._rated_current_a / i) ** (self._peukert_k - 1.0)
        if self._cell_c > self._thermal_derate_c:
            penalty = self._derate_slope_per_c * (self._cell_c - self._thermal_derate_c)
            c = c * max(0.1, 1.0 - penalty)
        return max(c, 1e-3)
