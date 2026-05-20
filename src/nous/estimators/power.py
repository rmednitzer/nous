"""Power state-of-charge estimator -- stub."""

from __future__ import annotations

from ..types import Estimate, Observation

__all__ = ["PowerEstimator"]


class PowerEstimator:
    """BL-027. Coulomb-counting + voltage Kalman update."""

    name: str = "power"

    def __init__(self) -> None:
        self._t = 0.0
        self._soc_pct = 100.0

    def predict(self, dt: float) -> None:
        self._t += dt

    def update(self, obs: Observation) -> None:
        if "soc_pct" in obs.payload:
            self._soc_pct = float(obs.payload["soc_pct"])

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={"soc_pct": self._soc_pct},
            covariance={"soc_pct": 1.0},
        )
