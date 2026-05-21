"""Power state-of-charge estimator: coulomb-counting plus voltage Kalman update.

The estimator runs a 1-D scalar Kalman filter over each of SoC and
terminal voltage. Process noise grows their covariances in
:meth:`predict`; observation noise from
:meth:`~nous.subsystems.power.PowerSubsystem.sensor_obs` shrinks them in
:meth:`update`. The last observed ``current_a`` is stored verbatim and
passed through in :meth:`state` -- it is not filtered and has no
covariance entry. See ``docs/model-cards/estimator-power-soc.md`` for
the covariance bound contract (BL-027 carries the full EKF; this v0.1
build ships the linear-Gaussian baseline).
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["PowerEstimator"]


_DEFAULT_INITIAL_SOC = 100.0
_DEFAULT_INITIAL_VOLTAGE = 14.4
_DEFAULT_SOC_SIGMA = 5.0
_DEFAULT_VOLTAGE_SIGMA = 0.5
_DEFAULT_SOC_PROCESS_SIGMA_PER_S = 0.05
_DEFAULT_VOLTAGE_PROCESS_SIGMA_PER_S = 0.01


class PowerEstimator:
    """1-D Kalman filter over SoC and terminal voltage (BL-027)."""

    name: str = "power"

    def __init__(
        self,
        initial_soc: float = _DEFAULT_INITIAL_SOC,
        initial_voltage: float = _DEFAULT_INITIAL_VOLTAGE,
        soc_sigma: float = _DEFAULT_SOC_SIGMA,
        voltage_sigma: float = _DEFAULT_VOLTAGE_SIGMA,
        soc_process_sigma_per_s: float = _DEFAULT_SOC_PROCESS_SIGMA_PER_S,
        voltage_process_sigma_per_s: float = _DEFAULT_VOLTAGE_PROCESS_SIGMA_PER_S,
    ) -> None:
        self._t = 0.0
        self._soc = float(initial_soc)
        self._soc_var = float(soc_sigma) ** 2
        self._voltage = float(initial_voltage)
        self._voltage_var = float(voltage_sigma) ** 2
        self._current = 0.0
        self._soc_q = float(soc_process_sigma_per_s) ** 2
        self._voltage_q = float(voltage_process_sigma_per_s) ** 2

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        self._soc_var += self._soc_q * dt
        self._voltage_var += self._voltage_q * dt

    def update(self, obs: Observation) -> None:
        payload = obs.payload
        noise = obs.noise

        soc = _finite(payload.get("soc_pct"))
        if soc is not None and 0.0 <= soc <= 100.0:
            r = float(noise.get("soc_pct_sigma", 0.5)) ** 2
            denom = self._soc_var + r
            if denom > 0.0:
                k = self._soc_var / denom
                self._soc = (1.0 - k) * self._soc + k * soc
                self._soc_var = (1.0 - k) * self._soc_var

        voltage = _finite(payload.get("voltage_v"))
        if voltage is not None and voltage >= 0.0:
            r = float(noise.get("voltage_v_sigma", 0.05)) ** 2
            denom = self._voltage_var + r
            if denom > 0.0:
                k = self._voltage_var / denom
                self._voltage = (1.0 - k) * self._voltage + k * voltage
                self._voltage_var = (1.0 - k) * self._voltage_var

        current = _finite(payload.get("current_a"))
        if current is not None:
            self._current = current

        ts = _finite(obs.ts_s)
        if ts is not None and ts >= 0.0:
            self._t = ts

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={
                "soc_pct": self._soc,
                "voltage_v": self._voltage,
                "current_a": self._current,
            },
            covariance={
                "soc_pct": self._soc_var,
                "voltage_v": self._voltage_var,
            },
        )


def _finite(value: object) -> float | None:
    """Return ``float(value)`` iff it is finite and convertible, else ``None``."""
    if value is None:
        return None
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v
