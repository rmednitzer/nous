"""Nonlinear position EKF: GNSS / INS fusion in a local ENU frame (BL-026).

The v0.1 position filter (:class:`~nous.estimators.position.PositionKalman`) kept
its state in degrees, which made the constant-velocity process and the direct GNSS
measurement both linear: a plain Kalman filter, not the EKF its own docstring
promised. This is that EKF. The state lives in a local east-north-up tangent frame
anchored on the first fix, carries ground speed in metres per second and heading in
radians, and is driven by the IMU: the longitudinal accelerometer integrates into
speed and the yaw-rate gyro into heading. GNSS corrects the east / north position.

The process is the unicycle model ``de = v sin(psi) dt``, ``dn = v cos(psi) dt``
(psi is clockwise from north, matching the position subsystem), so it is nonlinear
in psi and ``predict`` propagates the covariance through the analytic Jacobian. The
heading and speed are not measured directly; GNSS observes only position, and the
filter recovers v and psi through the cross-covariance the motion builds up, the
observability that earns the EKF its name (BL-026). Altitude stays a decoupled
scalar channel.

A GNSS fix whose normalised innovation exceeds the chi-square gate is rejected as
an outlier, but a jump that persists (an injected teleport, a re-acquired fix far
from the anchor) is adopted through a re-anchor reset rather than fought forever,
the same persist-then-reset discipline the scalar channels use. Input validation
refuses NaN / out-of-range coordinates without poisoning the estimate, and a filter
coasting without a fix raises ``dead_reckoning`` while its covariance grows.

The IMU bias is not estimated in this increment (a fixed accel / gyro bias drifts
the dead-reckoned solution during a GNSS outage, which is the realistic, visible
behaviour); error-state bias estimation is the follow-on.
"""

from __future__ import annotations

import math

import numpy as np

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, parse_bounded

__all__ = ["PositionEkf"]

_METERS_PER_DEG_LAT = 111_320.0
_Q_POS_PER_S = 0.5
_Q_SPEED_PER_S = 0.5
_Q_HEADING_PER_S = 0.05
_INIT_POS_VAR = 100.0
_INIT_SPEED_VAR = 4.0
_INIT_HEADING_VAR = 1.0
_POS_VAR_FLOOR = 1.0
# Chi-square 0.999 quantile, 2 dof: reject a GNSS innovation beyond it.
_GATE_CHI2_2DOF = 13.816
_RESET_AFTER = 3
_ALT_VAR_FLOOR = 0.01
_ALT_PROCESS_VAR_PER_S = 0.01


class PositionEkf:
    """Extended Kalman filter over ``[e, n, v, psi]`` in a local ENU frame."""

    name: str = "position"

    def __init__(self) -> None:
        self._t = 0.0
        self._x = np.zeros(4)  # [east_m, north_m, speed_mps, heading_rad]
        self._p = np.diag(
            [_INIT_POS_VAR, _INIT_POS_VAR, _INIT_SPEED_VAR, _INIT_HEADING_VAR]
        )
        self._anchor: tuple[float, float] | None = None
        self._accel = 0.0
        self._yaw_rate = 0.0
        self._alt = ScalarChannel(
            0.0,
            1e6,
            ChannelSpec(
                process_var_per_s=_ALT_PROCESS_VAR_PER_S,
                var_floor=_ALT_VAR_FLOOR,
                reset_after=_RESET_AFTER,
            ),
        )
        self._rejected = 0
        self._resets = 0
        self._consec_reject = 0
        self._fused = False
        self._fused_ever = False
        self._dead_reckoning = False
        self._last_nis = 0.0

    @property
    def rejected_updates(self) -> int:
        return self._rejected + self._alt.rejected

    def predict(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        e, n, v, psi = self._x
        s, c = math.sin(psi), math.cos(psi)
        self._x = np.array(
            [
                e + v * s * dt,
                n + v * c * dt,
                v + self._accel * dt,
                _wrap_angle(psi + self._yaw_rate * dt),
            ]
        )
        f = np.array(
            [
                [1.0, 0.0, s * dt, v * c * dt],
                [0.0, 1.0, c * dt, -v * s * dt],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]
        )
        q = np.diag(
            [
                _Q_POS_PER_S * dt,
                _Q_POS_PER_S * dt,
                _Q_SPEED_PER_S * dt,
                _Q_HEADING_PER_S * dt,
            ]
        )
        self._p = f @ self._p @ f.T + q
        self._alt.predict(dt)
        self._dead_reckoning = True

    def update(self, obs: Observation) -> None:
        if obs.source == "imu":
            self._accel = _finite(obs.payload.get("accel_mps2"), 0.0)
            self._yaw_rate = _finite(obs.payload.get("yaw_rate_rps"), 0.0)
            return
        if not obs.payload:
            self._dead_reckoning = True
            self._fused = False
            return
        lat = parse_bounded(obs.payload.get("lat"), -90.0, 90.0)
        lon = parse_bounded(obs.payload.get("lon"), -180.0, 180.0)
        if lat is None or lon is None:
            self._rejected += 1
            self._fused = False
            self._dead_reckoning = True
            return
        ts = float(obs.ts_s)
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

        anchor = self._anchor
        if anchor is None:
            anchor = (lat, lon)
            self._anchor = anchor
            self._x[0] = 0.0
            self._x[1] = 0.0

        e_meas, n_meas = _to_enu(lat, lon, anchor)
        cos_lat = max(1e-6, math.cos(math.radians(anchor[0])))
        r_e = (float(obs.noise.get("lon_sigma", 0.0)) * _METERS_PER_DEG_LAT * cos_lat) ** 2
        r_n = (float(obs.noise.get("lat_sigma", 0.0)) * _METERS_PER_DEG_LAT) ** 2
        r = np.diag([max(r_e, _POS_VAR_FLOOR), max(r_n, _POS_VAR_FLOOR)])
        h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        y = np.array([e_meas - self._x[0], n_meas - self._x[1]])
        s_mat = h @ self._p @ h.T + r
        try:
            s_inv = np.linalg.inv(s_mat)
        except np.linalg.LinAlgError:
            self._rejected += 1
            self._fused = False
            return
        nis = float(y @ s_inv @ y)
        self._last_nis = nis

        if self._fused_ever and (nis > _GATE_CHI2_2DOF or not math.isfinite(nis)):
            self._reject_or_reanchor(lat, lon)
            self._fuse_alt(obs)
            return

        k = self._p @ h.T @ s_inv
        self._x = self._x + k @ y
        self._x[3] = _wrap_angle(self._x[3])
        self._p = (np.eye(4) - k @ h) @ self._p
        self._p[0, 0] = max(float(self._p[0, 0]), _POS_VAR_FLOOR)
        self._p[1, 1] = max(float(self._p[1, 1]), _POS_VAR_FLOOR)
        self._fused = True
        self._fused_ever = True
        self._consec_reject = 0
        self._dead_reckoning = False
        self._fuse_alt(obs)

    def state(self) -> Estimate:
        e, n, v, psi = (float(self._x[i]) for i in range(4))
        if self._anchor is not None:
            lat0, lon0 = self._anchor
            cos_lat = max(1e-6, math.cos(math.radians(lat0)))
            lat = lat0 + n / _METERS_PER_DEG_LAT
            lon = lon0 + e / (_METERS_PER_DEG_LAT * cos_lat)
        else:
            lat, lon, cos_lat = 0.0, 0.0, 1.0
        point = {
            "lat": lat,
            "lon": lon,
            "alt_m": self._alt.value,
            "speed_mps": v,
            "heading_deg": math.degrees(psi) % 360.0,
            "v_e_mps": v * math.sin(psi),
            "v_n_mps": v * math.cos(psi),
        }
        covariance = {
            "lat": float(self._p[1, 1]) / (_METERS_PER_DEG_LAT**2),
            "lon": float(self._p[0, 0]) / ((_METERS_PER_DEG_LAT * cos_lat) ** 2),
            "alt_m": self._alt.var,
            "e_m": float(self._p[0, 0]),
            "n_m": float(self._p[1, 1]),
            "speed_mps": float(self._p[2, 2]),
            "heading_rad": float(self._p[3, 3]),
        }
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point=point,
            covariance=covariance,
            health=self._health(),
        )

    def _reject_or_reanchor(self, lat: float, lon: float) -> None:
        self._rejected += 1
        self._consec_reject += 1
        self._fused = False
        if self._consec_reject >= _RESET_AFTER:
            # A sustained jump is a real move (a teleport, a re-acquired fix):
            # re-anchor onto it rather than rejecting it forever.
            self._anchor = (lat, lon)
            self._x[0] = 0.0
            self._x[1] = 0.0
            self._p[0, 0] = _INIT_POS_VAR
            self._p[1, 1] = _INIT_POS_VAR
            self._consec_reject = 0
            self._resets += 1
            self._fused = True
            self._dead_reckoning = False

    def _fuse_alt(self, obs: Observation) -> None:
        alt = parse_bounded(obs.payload.get("alt_m"), -1000.0, 100_000.0)
        if alt is not None:
            self._alt.fuse(alt, float(obs.noise.get("alt_m_sigma", 0.0)) ** 2)

    def _health(self) -> EstimatorHealth:
        return EstimatorHealth(
            healthy=self._consec_reject < _RESET_AFTER,
            fused=self._fused,
            dead_reckoning=self._dead_reckoning,
            rejected_updates=self._rejected + self._alt.rejected,
            reset_count=self._resets + self._alt.resets,
            test_ratio={
                "position": round(self._last_nis, 6),
                "alt_m": round(self._alt.test_ratio, 6),
            },
            test_ratio_filtered={"alt_m": round(self._alt.test_ratio_filtered, 6)},
            innovation={"alt_m": round(self._alt.innovation, 6)},
        )


def _to_enu(lat: float, lon: float, anchor: tuple[float, float]) -> tuple[float, float]:
    lat0, lon0 = anchor
    cos_lat = max(1e-6, math.cos(math.radians(lat0)))
    e = (lon - lon0) * _METERS_PER_DEG_LAT * cos_lat
    n = (lat - lat0) * _METERS_PER_DEG_LAT
    return e, n


def _wrap_angle(psi: float) -> float:
    return (psi + math.pi) % (2.0 * math.pi) - math.pi


def _finite(raw: object, default: float) -> float:
    try:
        v = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default
