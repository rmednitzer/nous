"""Thermal Kalman filter (junction + enclosure two-state).

A linear Kalman filter over a two-state thermal model is the eventual home
for this estimator (BL-028). The wiring here keeps the predict / update /
state contract shared across the scalar estimators and folds each sensor
observation into the belief through a gated Kalman update: a reading whose
normalised innovation exceeds the gate is rejected, the posterior variance is
floored so a converged belief stays honest, and a sustained step (an injected
thermal load, a profile change) is adopted through a reset rather than fought
forever. The result is a calibrated, self-reporting belief over
``(junction_c, enclosure_c)`` that the self-model and
``self_estimator_status`` can read without owning subsystem state.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health

__all__ = ["ThermalKalman"]


_DEFAULT_JUNCTION_C = 25.0
_DEFAULT_ENCLOSURE_C = 25.0
_INITIAL_VARIANCE = 4.0
_PROCESS_VARIANCE_PER_S = 0.05
_FALLBACK_NOISE_SIGMA = 1.0


class ThermalKalman:
    """Two-state thermal filter (junction + enclosure) with innovation gating."""

    name: str = "thermal"

    def __init__(
        self,
        *,
        initial_junction_c: float = _DEFAULT_JUNCTION_C,
        initial_enclosure_c: float = _DEFAULT_ENCLOSURE_C,
    ) -> None:
        self._t = 0.0
        self._rejected = 0
        spec = ChannelSpec(process_var_per_s=_PROCESS_VARIANCE_PER_S)
        self._channels: dict[str, ScalarChannel] = {
            "junction_c": ScalarChannel(float(initial_junction_c), _INITIAL_VARIANCE, spec),
            "enclosure_c": ScalarChannel(float(initial_enclosure_c), _INITIAL_VARIANCE, spec),
        }

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        for channel in self._channels.values():
            channel.predict(dt)

    def update(self, obs: Observation) -> None:
        noise = obs.noise or {}
        for key, channel in self._channels.items():
            if key not in obs.payload:
                continue
            try:
                z = float(obs.payload[key])
            except (TypeError, ValueError):
                self._rejected += 1
                continue
            if not math.isfinite(z):
                self._rejected += 1
                continue
            r = float(noise.get(f"{key}_sigma", _FALLBACK_NOISE_SIGMA)) ** 2
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
