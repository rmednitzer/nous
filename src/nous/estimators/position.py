"""Position EKF over GNSS + IMU (BL-026).

Implements a constant-velocity kinematic Extended Kalman Filter over the
six-dimensional state ``(lat, lon, alt, v_lat, v_lon, v_alt)``. Lat and
lon are tracked in degrees; velocities are tracked in degrees-per-second
of the matching axis. The filter consumes GNSS observations (lat / lon
/ alt) from :class:`~nous.subsystems.position.PositionSubsystem` and
predicts the trajectory between fixes using the constant-velocity
process model.

Input validation refuses NaN / Inf / out-of-range coordinates without
poisoning the central estimate -- a rejected observation increments
:attr:`rejected_updates` and the filter falls back to predict-only.
The covariance grows over time without updates so the controller can
read divergence directly from the published sigmas.

The implementation deliberately stays diagonal (no cross-covariance
between lat / lon / alt) because the GNSS observation model is
diagonal and the constant-velocity decoupling between axes is exact in
the small-angle regime relevant to a backpack-class device. A full
6x6 EKF with cross-covariance is left for BL-061 (situational-awareness
fusion).
"""

from __future__ import annotations

import math

from ..types import Estimate, Observation

__all__ = ["PositionEKF"]


_INIT_POS_VAR = 1.0
_INIT_ALT_VAR = 1e6
_INIT_VEL_VAR = (5e-6) ** 2
_INIT_VEL_ALT_VAR = (0.1) ** 2
_PROCESS_POS_VAR_PER_S = (1e-7) ** 2
_PROCESS_ALT_VAR_PER_S = (0.01) ** 2
_PROCESS_VEL_VAR_PER_S = (1e-7) ** 2
_PROCESS_VEL_ALT_VAR_PER_S = (0.005) ** 2


class PositionEKF:
    """Constant-velocity EKF on lat / lon / alt + velocity components."""

    name: str = "position"

    def __init__(self) -> None:
        self._t = 0.0
        self._point: dict[str, float] = {
            "lat": 0.0,
            "lon": 0.0,
            "alt_m": 0.0,
            "v_lat": 0.0,
            "v_lon": 0.0,
            "v_alt_m": 0.0,
        }
        self._var: dict[str, float] = {
            "lat": _INIT_POS_VAR,
            "lon": _INIT_POS_VAR,
            "alt_m": _INIT_ALT_VAR,
            "v_lat": _INIT_VEL_VAR,
            "v_lon": _INIT_VEL_VAR,
            "v_alt_m": _INIT_VEL_ALT_VAR,
        }
        self._rejected = 0
        self._last_obs_ts: float | None = None

    @property
    def rejected_updates(self) -> int:
        """Count of observations refused on input validation."""
        return self._rejected

    def predict(self, dt: float) -> None:
        """Propagate state forward by ``dt`` seconds under constant-velocity."""
        if dt <= 0.0:
            return
        self._t += dt

        self._point["lat"] += self._point["v_lat"] * dt
        self._point["lon"] += self._point["v_lon"] * dt
        self._point["alt_m"] += self._point["v_alt_m"] * dt
        self._point["lat"] = max(-90.0, min(90.0, self._point["lat"]))
        self._point["lon"] = ((self._point["lon"] + 180.0) % 360.0) - 180.0

        self._var["lat"] += (
            self._var["v_lat"] * (dt**2) + _PROCESS_POS_VAR_PER_S * dt
        )
        self._var["lon"] += (
            self._var["v_lon"] * (dt**2) + _PROCESS_POS_VAR_PER_S * dt
        )
        self._var["alt_m"] += (
            self._var["v_alt_m"] * (dt**2) + _PROCESS_ALT_VAR_PER_S * dt
        )
        self._var["v_lat"] += _PROCESS_VEL_VAR_PER_S * dt
        self._var["v_lon"] += _PROCESS_VEL_VAR_PER_S * dt
        self._var["v_alt_m"] += _PROCESS_VEL_ALT_VAR_PER_S * dt

    def update(self, obs: Observation) -> None:
        """Fold a GNSS fix into the state.

        An empty payload (no fix) keeps the prediction branch -- the
        covariance has already widened under :meth:`predict`. Out-of
        range or non-finite values increment ``rejected_updates``
        without poisoning the estimate.

        Velocity is intentionally not derived from successive position
        observations: the noise floor on a backpack-class GNSS makes a
        differentiated-velocity estimator unstable. A future IMU
        observation channel will land the velocity state via a real
        sensor model.
        """
        if not obs.payload:
            return
        if not _validate(obs.payload):
            self._rejected += 1
            return

        for key in ("lat", "lon", "alt_m"):
            if key not in obs.payload:
                continue
            try:
                z = float(obs.payload[key])
            except (TypeError, ValueError):
                self._rejected += 1
                continue
            r = float(obs.noise.get(f"{key}_sigma", 0.0)) ** 2
            if r <= 0.0:
                self._point[key] = z
                continue
            p = self._var[key]
            s = p + r
            k = p / s
            innovation = z - self._point[key]
            if key == "lon":
                innovation = ((innovation + 180.0) % 360.0) - 180.0
            self._point[key] += k * innovation
            if key == "lon":
                self._point[key] = ((self._point[key] + 180.0) % 360.0) - 180.0
            self._var[key] = (1.0 - k) * p

        self._last_obs_ts = float(obs.ts_s)
        self._t = float(obs.ts_s)

    def state(self) -> Estimate:
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=dict(self._point),
            covariance=dict(self._var),
        )


def _validate(payload: dict[str, object]) -> bool:
    """Reject NaN/Inf and out-of-range lat/lon/alt before the filter eats them."""
    for key, value in payload.items():
        if key not in ("lat", "lon", "alt_m"):
            continue
        try:
            v = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        if not math.isfinite(v):
            return False
        if key == "lat" and not -90.0 <= v <= 90.0:
            return False
        if key == "lon" and not -180.0 <= v <= 180.0:
            return False
        if key == "alt_m" and not -1000.0 <= v <= 100_000.0:
            return False
    return True
