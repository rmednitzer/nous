"""Position subsystem: ground truth, dead reckoning, GNSS fix gating (BL-010).

The simulator carries the operator's lat / lon / alt as ground truth
and steps it forward each tick from a velocity + heading dead-reckoning
model. GNSS noise sigmas come from
``profile["sensors"]["position"]`` so the position estimator's Kalman
gain is sized by the appliance's actual sensor envelope. When the
scenario clears the fix flag (a covered antenna, urban canyon, jammer)
the subsystem still advances ground truth via the IMU dead-reckoning
path but stops emitting lat / lon / alt in the GNSS observation; the
estimator's variance grows under ``predict`` until a fix returns.

Controller seams:

* :meth:`set_position` -- teleport ground truth (scenario seed).
* :meth:`set_velocity` -- speed in metres per second on a true bearing
  (heading in degrees clockwise from north).
* :meth:`set_fix` -- toggle GNSS fix; without a fix the GNSS sensor
  reports an empty payload (the IMU is not lost, only the absolute
  reference is).
* :meth:`set_imu_drift` -- per-second velocity bias applied when the
  fix is lost (lets a scenario express "the IMU is biased north at 0.5
  m/s while you're under cover").

The full GNSS+IMU fusion filter is BL-026; this subsystem feeds the v0.1
pass-through :class:`~nous.estimators.position.PositionKalman`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from ..types import Observation

__all__ = ["PositionSubsystem"]


_METERS_PER_DEG_LAT = 111_320.0
_DEFAULT_LAT = 47.0
_DEFAULT_LON = 13.0
_DEFAULT_ALT = 500.0
_DEFAULT_LAT_SIGMA = 3.0e-5
_DEFAULT_LON_SIGMA = 3.0e-5
_DEFAULT_ALT_SIGMA = 5.0
_DEFAULT_FIX_RATE_HZ = 10.0


class PositionSubsystem:
    """Lat / lon / alt ground truth with profile-driven GNSS noise."""

    name: str = "position"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.profile = profile
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        cfg = dict((profile.get("sensors") or {}).get("position") or {})
        self._lat_sigma = float(cfg.get("lat_sigma", _DEFAULT_LAT_SIGMA))
        self._lon_sigma = float(cfg.get("lon_sigma", _DEFAULT_LON_SIGMA))
        self._alt_sigma = float(cfg.get("alt_m_sigma", _DEFAULT_ALT_SIGMA))
        self._fix_rate_hz = float(cfg.get("fix_rate_hz", _DEFAULT_FIX_RATE_HZ))

        self._t = 0.0
        self._lat = _DEFAULT_LAT
        self._lon = _DEFAULT_LON
        self._alt_m = _DEFAULT_ALT
        self._speed_mps = 0.0
        self._heading_deg = 0.0
        self._vertical_mps = 0.0
        self._has_fix = True
        self._imu_drift_north_mps = 0.0
        self._imu_drift_east_mps = 0.0
        self._dead_reckoning_s = 0.0

    def set_position(
        self, lat: float, lon: float, alt_m: float | None = None
    ) -> None:
        """Teleport ground truth to ``(lat, lon)`` and optionally ``alt_m``."""
        self._lat = max(-90.0, min(90.0, float(lat)))
        self._lon = _wrap_lon(float(lon))
        if alt_m is not None:
            self._alt_m = float(alt_m)

    def set_velocity(
        self,
        speed_mps: float,
        heading_deg: float,
        *,
        vertical_mps: float = 0.0,
    ) -> None:
        """Dead-reckoning velocity vector (speed + bearing + vertical)."""
        self._speed_mps = max(0.0, float(speed_mps))
        self._heading_deg = float(heading_deg) % 360.0
        self._vertical_mps = float(vertical_mps)

    def set_fix(self, has_fix: bool) -> None:
        """Toggle GNSS fix availability."""
        if has_fix:
            self._dead_reckoning_s = 0.0
        self._has_fix = bool(has_fix)

    def set_imu_drift(self, north_mps: float = 0.0, east_mps: float = 0.0) -> None:
        """Velocity bias applied when GNSS fix is lost."""
        self._imu_drift_north_mps = float(north_mps)
        self._imu_drift_east_mps = float(east_mps)

    @property
    def lat(self) -> float:
        return self._lat

    @property
    def lon(self) -> float:
        return self._lon

    @property
    def alt_m(self) -> float:
        return self._alt_m

    @property
    def speed_mps(self) -> float:
        return self._speed_mps

    @property
    def heading_deg(self) -> float:
        return self._heading_deg

    @property
    def has_fix(self) -> bool:
        return self._has_fix

    @property
    def dead_reckoning_s(self) -> float:
        """Seconds since the last GNSS fix (0 while a fix is held)."""
        return self._dead_reckoning_s

    @property
    def fix_rate_hz(self) -> float:
        return self._fix_rate_hz

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        heading_rad = math.radians(self._heading_deg)
        north_mps = self._speed_mps * math.cos(heading_rad)
        east_mps = self._speed_mps * math.sin(heading_rad)
        if not self._has_fix:
            north_mps += self._imu_drift_north_mps
            east_mps += self._imu_drift_east_mps
            self._dead_reckoning_s += dt
        dn_m = north_mps * dt
        de_m = east_mps * dt
        if dn_m or de_m:
            cos_lat = max(1e-6, math.cos(math.radians(self._lat)))
            dlat = dn_m / _METERS_PER_DEG_LAT
            dlon = de_m / (_METERS_PER_DEG_LAT * cos_lat)
            self._lat = max(-90.0, min(90.0, self._lat + dlat))
            self._lon = _wrap_lon(self._lon + dlon)
        if self._vertical_mps:
            self._alt_m += self._vertical_mps * dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "lat": self._lat,
            "lon": self._lon,
            "alt_m": self._alt_m,
            "speed_mps": self._speed_mps,
            "heading_deg": self._heading_deg,
            "vertical_mps": self._vertical_mps,
            "has_fix": self._has_fix,
            "dead_reckoning_s": self._dead_reckoning_s,
            "fix_rate_hz": self._fix_rate_hz,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        """GNSS observation. Empty payload when the fix is lost."""
        if self._has_fix:
            payload: dict[str, Any] = {
                "lat": self._lat,
                "lon": self._lon,
                "alt_m": self._alt_m,
            }
            noise: dict[str, Any] = {
                "lat_sigma": self._lat_sigma,
                "lon_sigma": self._lon_sigma,
                "alt_m_sigma": self._alt_sigma,
            }
        else:
            payload = {}
            noise = {}
        return Observation(
            source=self.name, ts_s=self._t, payload=payload, noise=noise
        )


def _wrap_lon(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0
