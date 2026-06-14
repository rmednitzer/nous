"""Position Kalman filter over GNSS fixes (BL-026).

Implements a constant-velocity kinematic Kalman filter over the
six-dimensional state ``(lat, lon, alt, v_lat, v_lon, v_alt)``. Lat and lon
are tracked in degrees; velocities are tracked in degrees-per-second of the
matching axis. Because the state stays in degrees (not metres), both the
constant-velocity process model and the direct GNSS measurement model are
linear, so this is a plain linear Kalman filter, not an EKF: there is no
Jacobian and no linearisation step. A genuine EKF only earns its name once
the state carries body-frame velocity in m/s or a range/bearing measurement,
either of which couples the axes through ``cos(lat)``; that lands with the
IMU-fusion track, tracked under BL-026 (this estimator's own id).

The lat / lon / alt channels fuse through the shared gated Kalman update
(:mod:`nous.estimators.health`): a fix whose normalised innovation exceeds
the gate is rejected as an outlier, but a fix that *persists* (a genuine jump,
an injected teleport) is adopted through a reset rather than fought forever,
and the reset is counted so the controller can see it. Each position channel
floors its posterior variance at a GNSS-realistic value, so the filter never
reports the falsely certain zero a noiseless one-step collapse would produce.

Input validation refuses NaN / Inf / out-of-range coordinates without
poisoning the central estimate; a rejected fix increments
:attr:`rejected_updates` and the filter coasts on prediction. When the filter
is coasting (no fix, or a rejected fix) its health block raises
``dead_reckoning`` so the controller knows the position is drifting.

The implementation deliberately stays diagonal (no cross-covariance between
lat / lon / alt) because the GNSS observation model is diagonal and the
constant-velocity decoupling between axes is exact in the small-angle regime
relevant to a backpack-class device. A full 6x6 filter with cross-covariance
is the IMU-fusion continuation tracked under BL-026; the self-model
situational-awareness fusion that consumes this estimate is BL-061.
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health

__all__ = ["PositionKalman"]


_INIT_POS_VAR = 1.0
_INIT_ALT_VAR = 1e6
_INIT_VEL_VAR = (5e-6) ** 2
_INIT_VEL_ALT_VAR = (0.1) ** 2
_PROCESS_POS_VAR_PER_S = (1e-7) ** 2
_PROCESS_ALT_VAR_PER_S = (0.01) ** 2
_PROCESS_VEL_VAR_PER_S = (1e-7) ** 2
_PROCESS_VEL_ALT_VAR_PER_S = (0.005) ** 2
# Floors below which a GNSS solution cannot honestly claim to know its own
# position: roughly 1 m horizontally and 0.1 m vertically. They replace the
# false-certainty zero a one-step collapse used to report.
_LATLON_VAR_FLOOR = 1e-10
_ALT_VAR_FLOOR = 0.01
# A jump that persists for this many fixes is a real move, not an outlier;
# the channel resets onto it (and counts the reset) rather than rejecting it.
_POS_RESET_AFTER = 3


class PositionKalman:
    """Constant-velocity linear Kalman filter on lat / lon / alt + velocity."""

    name: str = "position"

    def __init__(self) -> None:
        self._t = 0.0
        self._rejected = 0
        self._dead_reckoning = False
        self._last_obs_ts: float | None = None
        self._pos: dict[str, ScalarChannel] = {
            "lat": ScalarChannel(
                0.0,
                _INIT_POS_VAR,
                ChannelSpec(var_floor=_LATLON_VAR_FLOOR, reset_after=_POS_RESET_AFTER),
            ),
            "lon": ScalarChannel(
                0.0,
                _INIT_POS_VAR,
                ChannelSpec(var_floor=_LATLON_VAR_FLOOR, reset_after=_POS_RESET_AFTER),
            ),
            "alt_m": ScalarChannel(
                0.0,
                _INIT_ALT_VAR,
                ChannelSpec(var_floor=_ALT_VAR_FLOOR, reset_after=_POS_RESET_AFTER),
            ),
        }
        self._vel: dict[str, float] = {"v_lat": 0.0, "v_lon": 0.0, "v_alt_m": 0.0}
        self._vel_var: dict[str, float] = {
            "v_lat": _INIT_VEL_VAR,
            "v_lon": _INIT_VEL_VAR,
            "v_alt_m": _INIT_VEL_ALT_VAR,
        }

    @property
    def rejected_updates(self) -> int:
        """Count of fixes refused on input validation or, by extension, the gate."""
        return self._rejected + sum(c.rejected for c in self._pos.values())

    def predict(self, dt: float) -> None:
        """Propagate state forward by ``dt`` seconds under constant velocity.

        The variance growth is coupled across position and velocity, so it is
        applied here directly rather than through the channels' own process
        noise (their ``process_var_per_s`` is left at zero).
        """
        if dt <= 0.0:
            return
        self._t += dt

        lat, lon, alt = self._pos["lat"], self._pos["lon"], self._pos["alt_m"]
        lat.value += self._vel["v_lat"] * dt
        lon.value += self._vel["v_lon"] * dt
        alt.value += self._vel["v_alt_m"] * dt
        lat.value = max(-90.0, min(90.0, lat.value))
        lon.value = ((lon.value + 180.0) % 360.0) - 180.0

        lat.var += self._vel_var["v_lat"] * (dt**2) + _PROCESS_POS_VAR_PER_S * dt
        lon.var += self._vel_var["v_lon"] * (dt**2) + _PROCESS_POS_VAR_PER_S * dt
        alt.var += self._vel_var["v_alt_m"] * (dt**2) + _PROCESS_ALT_VAR_PER_S * dt
        self._vel_var["v_lat"] += _PROCESS_VEL_VAR_PER_S * dt
        self._vel_var["v_lon"] += _PROCESS_VEL_VAR_PER_S * dt
        self._vel_var["v_alt_m"] += _PROCESS_VEL_ALT_VAR_PER_S * dt

    def update(self, obs: Observation) -> None:
        """Fold a GNSS fix into the state.

        An empty payload (no fix) keeps the prediction branch and raises
        ``dead_reckoning``: the covariance has already widened under
        :meth:`predict`. Out-of-range or non-finite values increment
        ``rejected_updates`` without poisoning the estimate.

        Velocity is intentionally not derived from successive position
        observations: the noise floor on a backpack-class GNSS makes a
        differentiated-velocity estimator unstable. A future IMU observation
        channel will land the velocity state via a real sensor model.
        """
        if not obs.payload:
            self._dead_reckoning = True
            return
        if not _validate(obs.payload):
            self._rejected += 1
            self._dead_reckoning = True
            return

        fused_any = False
        for key, channel in self._pos.items():
            if key not in obs.payload:
                continue
            z = float(obs.payload[key])
            r = float(obs.noise.get(f"{key}_sigma", 0.0)) ** 2
            if key == "lon":
                innovation = ((z - channel.value + 180.0) % 360.0) - 180.0
                channel.fuse_innovation(innovation, r)
                channel.value = ((channel.value + 180.0) % 360.0) - 180.0
            else:
                channel.fuse(z, r)
            fused_any = fused_any or channel.fused

        self._dead_reckoning = not fused_any
        ts = float(obs.ts_s)
        if math.isfinite(ts) and ts >= 0.0:
            self._last_obs_ts = ts
            self._t = ts

    def health(self) -> EstimatorHealth:
        return build_health(
            self._pos,
            rejected_extra=self._rejected,
            dead_reckoning=self._dead_reckoning,
            fused_override=not self._dead_reckoning,
        )

    def state(self) -> Estimate:
        point = {key: c.value for key, c in self._pos.items()}
        point.update(self._vel)
        covariance: dict[str, float] = {key: c.var for key, c in self._pos.items()}
        covariance.update(self._vel_var)
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=point,
            covariance=covariance,
            health=self.health(),
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
