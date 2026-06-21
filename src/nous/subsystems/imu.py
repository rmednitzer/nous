"""IMU subsystem: strapdown gyro + accelerometer ground truth (BL-026).

The moving platform carries an inertial measurement unit. This subsystem models
the two channels a ground-vehicle / backpack strapdown IMU contributes to a
GNSS/INS fusion filter: a body-frame longitudinal accelerometer (the platform's
along-track specific force) and a yaw-rate gyro (its turn rate). Both are derived
from the platform's own motion: the engine feeds the position subsystem's current
speed and heading each tick (:meth:`set_motion`), and ``step`` differentiates them
into a true acceleration and yaw rate.

The measured observation is the truth plus a slowly-drifting bias (a random walk on
the engine RNG, ADR 0019) plus white noise, the standard IMU error model. The truth
carries the bias separately, so a downstream filter can be scored against it.
Profile fields live under ``sensors.imu`` (``accel_sigma`` / ``gyro_sigma`` white
noise, ``accel_bias_walk`` / ``gyro_bias_walk`` bias instability, optional
``accel_bias`` / ``gyro_bias`` seeds); all default to a small, sane envelope so an
unconfigured profile gets a usable IMU.

The nonlinear EKF (:class:`~nous.estimators.position_ekf.PositionEkf`) consumes this
observation as the control that drives its prediction; GNSS corrects the result.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from ..types import Observation

__all__ = ["ImuSubsystem"]

_DEFAULT_ACCEL_SIGMA = 0.05  # m/s^2 white noise
_DEFAULT_GYRO_SIGMA = 0.002  # rad/s white noise
_DEFAULT_ACCEL_BIAS_WALK = 0.001  # m/s^2 per sqrt(s)
_DEFAULT_GYRO_BIAS_WALK = 0.0001  # rad/s per sqrt(s)


class ImuSubsystem:
    """Body-frame longitudinal accelerometer + yaw-rate gyro from platform motion."""

    name: str = "imu"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        self.profile = profile
        cfg = dict((profile.get("sensors") or {}).get("imu") or {})
        self._accel_sigma = max(0.0, float(cfg.get("accel_sigma", _DEFAULT_ACCEL_SIGMA)))
        self._gyro_sigma = max(0.0, float(cfg.get("gyro_sigma", _DEFAULT_GYRO_SIGMA)))
        self._accel_bias_walk = max(
            0.0, float(cfg.get("accel_bias_walk", _DEFAULT_ACCEL_BIAS_WALK))
        )
        self._gyro_bias_walk = max(
            0.0, float(cfg.get("gyro_bias_walk", _DEFAULT_GYRO_BIAS_WALK))
        )
        self._accel_bias = float(cfg.get("accel_bias", 0.0))
        self._gyro_bias = float(cfg.get("gyro_bias", 0.0))
        self._t = 0.0
        self._speed_mps = 0.0
        self._heading_deg = 0.0
        self._prev_speed = 0.0
        self._prev_heading = 0.0
        self._accel_true = 0.0
        self._yaw_rate_true = 0.0

    def set_motion(self, speed_mps: float, heading_deg: float) -> None:
        """Engine seam: the platform's current commanded speed and heading."""
        self._speed_mps = max(0.0, float(speed_mps))
        self._heading_deg = float(heading_deg) % 360.0

    def set_bias(
        self,
        *,
        accel_bias: float | None = None,
        gyro_bias: float | None = None,
        freeze_walk: bool = False,
    ) -> None:
        """Inject a known inertial-sensor bias (a scenario fault, a test seam).

        ``freeze_walk`` pins the bias by zeroing the random-walk instability, so an
        injected bias stays constant for a filter to converge against.
        """
        if accel_bias is not None:
            self._accel_bias = float(accel_bias)
        if gyro_bias is not None:
            self._gyro_bias = float(gyro_bias)
        if freeze_walk:
            self._accel_bias_walk = 0.0
            self._gyro_bias_walk = 0.0

    @property
    def accel_mps2(self) -> float:
        return self._accel_true

    @property
    def yaw_rate_rps(self) -> float:
        return self._yaw_rate_true

    @property
    def accel_bias(self) -> float:
        return self._accel_bias

    @property
    def gyro_bias(self) -> float:
        return self._gyro_bias

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        self._accel_true = (self._speed_mps - self._prev_speed) / dt
        dheading = ((self._heading_deg - self._prev_heading + 180.0) % 360.0) - 180.0
        self._yaw_rate_true = math.radians(dheading) / dt
        self._prev_speed = self._speed_mps
        self._prev_heading = self._heading_deg
        if self._rng is not None:
            walk = math.sqrt(dt)
            self._accel_bias += float(self._rng.normal(0.0, self._accel_bias_walk * walk))
            self._gyro_bias += float(self._rng.normal(0.0, self._gyro_bias_walk * walk))

    def truth(self) -> Mapping[str, Any]:
        return {
            "accel_mps2": self._accel_true,
            "yaw_rate_rps": self._yaw_rate_true,
            "accel_bias": self._accel_bias,
            "gyro_bias": self._gyro_bias,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        accel_noise = 0.0
        gyro_noise = 0.0
        if self._rng is not None:
            accel_noise = float(self._rng.normal(0.0, self._accel_sigma))
            gyro_noise = float(self._rng.normal(0.0, self._gyro_sigma))
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "accel_mps2": self._accel_true + self._accel_bias + accel_noise,
                "yaw_rate_rps": self._yaw_rate_true + self._gyro_bias + gyro_noise,
            },
            noise={
                "accel_mps2_sigma": self._accel_sigma,
                "yaw_rate_rps_sigma": self._gyro_sigma,
            },
        )
