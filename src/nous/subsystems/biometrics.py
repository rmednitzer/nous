"""Operator biometrics subsystem (BL-011).

Parametric, not physiology-grounded: ``nous`` simulates an inference
appliance, not a person. The biometrics subsystem carries four
controller-visible scalars as ground truth -- heart rate, core
temperature, hydration percentage, and a unitless cognitive-load proxy
-- and exposes scenario seams so a runbook can express "the operator
sprinted up a hill, HR 170, core temp climbing" or "they've been on
patrol for six hours, hydration is at 60 percent" without inventing
biology.

Profile fields under ``sensors.biometrics`` are the calibrated sensor
sigmas; defaults are kept narrow because the wearable kit's published
spec is the same across the canonical profiles. Defaults for the
state itself (resting HR 70, core temp 37, hydration 90, cognitive
load 0.2) match the controller's expected "nominal" envelope.

The paired :class:`~nous.estimators.biometrics.BiometricsKalman` is
already a real multi-channel filter with physiological-bounds
validation; this PR adds ``hydration_pct`` to its tracked channels
and wires the subsystem into the engine tick. A full L2 physiology
model (cardiovascular response curves, thermoregulation) remains out
of scope.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..types import Observation

__all__ = ["BiometricsSubsystem"]


_DEFAULT_HEART_RATE_BPM = 70.0
_DEFAULT_CORE_TEMP_C = 37.0
_DEFAULT_HYDRATION_PCT = 90.0
_DEFAULT_COGNITIVE_LOAD = 0.2
_DEFAULT_HEART_RATE_SIGMA = 2.0
_DEFAULT_CORE_TEMP_SIGMA = 0.05
_DEFAULT_HYDRATION_SIGMA = 1.0
_DEFAULT_COGNITIVE_LOAD_SIGMA = 0.05
_HR_MIN = 20.0
_HR_MAX = 240.0
_CORE_TEMP_MIN = 28.0
_CORE_TEMP_MAX = 44.0


class BiometricsSubsystem:
    """Parametric biometrics ground truth + scenario seams."""

    name: str = "biometrics"

    def __init__(self, profile: Mapping[str, Any]) -> None:
        self.profile = profile
        cfg = dict((profile.get("sensors") or {}).get("biometrics") or {})
        self._hr_sigma = float(
            cfg.get("heart_rate_bpm_sigma", _DEFAULT_HEART_RATE_SIGMA)
        )
        self._core_temp_sigma = float(
            cfg.get("core_temp_c_sigma", _DEFAULT_CORE_TEMP_SIGMA)
        )
        self._hydration_sigma = float(
            cfg.get("hydration_pct_sigma", _DEFAULT_HYDRATION_SIGMA)
        )
        self._cognitive_load_sigma = float(
            cfg.get("cognitive_load_sigma", _DEFAULT_COGNITIVE_LOAD_SIGMA)
        )
        self._t = 0.0
        self._heart_rate_bpm = _clamp_hr(
            float(cfg.get("heart_rate_bpm_default", _DEFAULT_HEART_RATE_BPM))
        )
        self._core_temp_c = _clamp_core_temp(
            float(cfg.get("core_temp_c_default", _DEFAULT_CORE_TEMP_C))
        )
        self._hydration_pct = _clamp_pct(
            float(cfg.get("hydration_pct_default", _DEFAULT_HYDRATION_PCT))
        )
        self._cognitive_load = _clamp_unit(
            float(cfg.get("cognitive_load_default", _DEFAULT_COGNITIVE_LOAD))
        )

    def set_heart_rate_bpm(self, hr_bpm: float) -> None:
        self._heart_rate_bpm = _clamp_hr(float(hr_bpm))

    def set_core_temp_c(self, core_temp_c: float) -> None:
        self._core_temp_c = _clamp_core_temp(float(core_temp_c))

    def set_hydration_pct(self, hydration_pct: float) -> None:
        self._hydration_pct = _clamp_pct(float(hydration_pct))

    def set_cognitive_load(self, cognitive_load: float) -> None:
        self._cognitive_load = _clamp_unit(float(cognitive_load))

    @property
    def heart_rate_bpm(self) -> float:
        return self._heart_rate_bpm

    @property
    def core_temp_c(self) -> float:
        return self._core_temp_c

    @property
    def hydration_pct(self) -> float:
        return self._hydration_pct

    @property
    def cognitive_load(self) -> float:
        return self._cognitive_load

    @property
    def heart_rate_sigma(self) -> float:
        return self._hr_sigma

    @property
    def core_temp_sigma(self) -> float:
        return self._core_temp_sigma

    @property
    def hydration_sigma(self) -> float:
        return self._hydration_sigma

    @property
    def cognitive_load_sigma(self) -> float:
        return self._cognitive_load_sigma

    def step(self, dt: float) -> None:
        if dt > 0.0:
            self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "heart_rate_bpm": self._heart_rate_bpm,
            "core_temp_c": self._core_temp_c,
            "hydration_pct": self._hydration_pct,
            "cognitive_load": self._cognitive_load,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "heart_rate_bpm": self._heart_rate_bpm,
                "core_temp_c": self._core_temp_c,
                "hydration_pct": self._hydration_pct,
                "cognitive_load": self._cognitive_load,
            },
            noise={
                "heart_rate_bpm_sigma": self._hr_sigma,
                "core_temp_c_sigma": self._core_temp_sigma,
                "hydration_pct_sigma": self._hydration_sigma,
                "cognitive_load_sigma": self._cognitive_load_sigma,
            },
        )


def _clamp_hr(value: float) -> float:
    return max(_HR_MIN, min(_HR_MAX, value))


def _clamp_core_temp(value: float) -> float:
    return max(_CORE_TEMP_MIN, min(_CORE_TEMP_MAX, value))


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))
