"""Thermal Kalman filter (junction + enclosure two-state).

A linear Kalman filter over a two-state thermal model is the eventual
home for this estimator (BL-028). The L1 wiring here keeps the same
predict / update / state contract as the power estimator and folds
each sensor observation into the belief via a per-channel Kalman
gain: ``belief = (1 - k) * belief + k * obs``, with the posterior
variance ``var = (1 - k) * var``. The result is a calibrated belief
over ``(junction_c, enclosure_c)`` that the self-model and
``self_estimator_status`` can read without owning subsystem state.
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["ThermalKalman"]


_DEFAULT_JUNCTION_C = 25.0
_DEFAULT_ENCLOSURE_C = 25.0
_INITIAL_VARIANCE = 4.0
_PROCESS_VARIANCE_PER_S = 0.05
_FALLBACK_NOISE_SIGMA = 1.0


class ThermalKalman:
    """L1 two-state thermal filter (junction + enclosure).

    Predict adds process noise per second; update folds each channel of
    the noisy sensor reading toward the prior with a Kalman gain. The
    update also resynchronises ``_t`` to ``obs.ts_s`` so the estimator's
    timestamp matches the observation stream even if ``predict`` was
    skipped or the tick cadence drifted (matches the PowerEstimator /
    ApuEstimator contract).
    """

    name: str = "thermal"

    def __init__(
        self,
        *,
        initial_junction_c: float = _DEFAULT_JUNCTION_C,
        initial_enclosure_c: float = _DEFAULT_ENCLOSURE_C,
    ) -> None:
        self._t = 0.0
        self._junction_c = float(initial_junction_c)
        self._enclosure_c = float(initial_enclosure_c)
        self._var_j = _INITIAL_VARIANCE
        self._var_e = _INITIAL_VARIANCE

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        self._var_j += _PROCESS_VARIANCE_PER_S * dt
        self._var_e += _PROCESS_VARIANCE_PER_S * dt

    def update(self, obs: Observation) -> None:
        noise = obs.noise or {}
        if "junction_c" in obs.payload:
            r = float(noise.get("junction_c_sigma", _FALLBACK_NOISE_SIGMA)) ** 2
            k = self._var_j / (self._var_j + max(r, 1e-6))
            self._junction_c = self._junction_c + k * (
                float(obs.payload["junction_c"]) - self._junction_c
            )
            self._var_j = (1.0 - k) * self._var_j
        if "enclosure_c" in obs.payload:
            r = float(noise.get("enclosure_c_sigma", _FALLBACK_NOISE_SIGMA)) ** 2
            k = self._var_e / (self._var_e + max(r, 1e-6))
            self._enclosure_c = self._enclosure_c + k * (
                float(obs.payload["enclosure_c"]) - self._enclosure_c
            )
            self._var_e = (1.0 - k) * self._var_e
        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={
                "junction_c": self._junction_c,
                "enclosure_c": self._enclosure_c,
            },
            covariance={"junction_c": self._var_j, "enclosure_c": self._var_e},
        )
