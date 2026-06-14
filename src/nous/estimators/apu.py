"""APU output estimator: per-source gated Kalman smoothing.

Tracks the four APU sources (solar, fuel cell, vehicle tether, USB-C PD) plus
the total. Each channel is a scalar Kalman filter whose process noise grows in
:meth:`predict` and is folded toward the matching observation through a gated
Kalman update in :meth:`update`. The covariance bounds are loose relative to
the power SoC estimator: the APU mostly reports its own configuration, not a
hidden physical state, so the gate is generous and exists mainly to reject a
non-finite reading and to surface a persistent disagreement in the health
block.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health

__all__ = ["ApuEstimator"]


_FIELDS: tuple[str, ...] = (
    "solar_w",
    "fuelcell_w",
    "vehicle_w",
    "usbc_w",
    "total_w",
)

_DEFAULT_INITIAL_SIGMA = 2.0
_DEFAULT_PROCESS_SIGMA_PER_S = 0.2
_FALLBACK_SIGMA = 1.0
# The APU reports configuration rather than a hidden state, so a wide gate
# keeps legitimate setpoint changes flowing while still catching garbage.
_APU_GATE_SIGMA = 8.0


class ApuEstimator:
    """Per-source gated Kalman smoothing for APU outputs."""

    name: str = "apu"

    def __init__(
        self,
        initial_sigma: float = _DEFAULT_INITIAL_SIGMA,
        process_sigma_per_s: float = _DEFAULT_PROCESS_SIGMA_PER_S,
    ) -> None:
        self._t = 0.0
        self._rejected = 0
        spec = ChannelSpec(
            process_var_per_s=float(process_sigma_per_s) ** 2,
            gate_sigma=_APU_GATE_SIGMA,
        )
        self._channels: dict[str, ScalarChannel] = {
            key: ScalarChannel(0.0, float(initial_sigma) ** 2, spec) for key in _FIELDS
        }

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for channel in self._channels.values():
            channel.predict(dt)

    def update(self, obs: Observation) -> None:
        noise = obs.noise
        payload = obs.payload
        for key, channel in self._channels.items():
            if key not in payload:
                continue
            try:
                z = float(payload[key])
            except (TypeError, ValueError):
                self._rejected += 1
                continue
            if not math.isfinite(z):
                self._rejected += 1
                continue
            r = float(noise.get(f"{key}_sigma", _FALLBACK_SIGMA)) ** 2
            channel.fuse(z, r)
        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def health(self) -> EstimatorHealth:
        return build_health(self._channels, rejected_extra=self._rejected)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={key: c.value for key, c in self._channels.items()},
            covariance={key: c.var for key, c in self._channels.items()},
            health=self.health(),
        )
