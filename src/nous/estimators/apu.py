"""APU output estimator: per-source first-order Kalman smoothing.

Tracks the five APU sources (solar, fuel cell, vehicle tether, USB-C PD,
hand-crank) plus the total. Each channel is a scalar Kalman filter whose
process noise grows in :meth:`predict` and is shrunk by the matching
sensor observation in :meth:`update`. The covariance bounds are loose
relative to the power SoC estimator -- the APU mostly reports its own
configuration, not a hidden physical state.
"""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["ApuEstimator"]


_FIELDS: tuple[str, ...] = (
    "solar_w",
    "fuelcell_w",
    "vehicle_w",
    "usbc_w",
    "hand_crank_w",
    "total_w",
)

_DEFAULT_INITIAL_SIGMA = 2.0
_DEFAULT_PROCESS_SIGMA_PER_S = 0.2


class ApuEstimator:
    """Per-source Kalman smoothing for APU outputs."""

    name: str = "apu"

    def __init__(
        self,
        initial_sigma: float = _DEFAULT_INITIAL_SIGMA,
        process_sigma_per_s: float = _DEFAULT_PROCESS_SIGMA_PER_S,
    ) -> None:
        self._t = 0.0
        self._values: dict[str, float] = dict.fromkeys(_FIELDS, 0.0)
        self._vars: dict[str, float] = dict.fromkeys(_FIELDS, float(initial_sigma) ** 2)
        self._q = float(process_sigma_per_s) ** 2

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        bump = self._q * dt
        for key in _FIELDS:
            self._vars[key] += bump

    def update(self, obs: Observation) -> None:
        payload = obs.payload
        noise = obs.noise
        for key in _FIELDS:
            if key not in payload:
                continue
            r = float(noise.get(f"{key}_sigma", 1.0)) ** 2
            denom = self._vars[key] + r
            if denom <= 0.0:
                continue
            k = self._vars[key] / denom
            self._values[key] = (1.0 - k) * self._values[key] + k * float(payload[key])
            self._vars[key] = (1.0 - k) * self._vars[key]
        self._t = float(obs.ts_s)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=dict(self._values),
            covariance=dict(self._vars),
        )
