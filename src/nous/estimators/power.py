"""Power state-of-charge estimator: gated Kalman over SoC and voltage.

The estimator runs a scalar Kalman filter over each of SoC, terminal voltage,
and total electrical load (``load_w``, ADR 0083). Process noise grows their
covariances in :meth:`predict`; an
observation from
:meth:`~nous.subsystems.power.PowerSubsystem.sensor_obs` folds in through a
gated Kalman update in :meth:`update`. Each channel rejects a measurement
whose normalised innovation exceeds the gate, floors its posterior variance
so a converged belief stays honest about residual sensor noise, and adopts a
sustained disagreement through a reset rather than fighting it forever (see
:mod:`nous.estimators.health`). The last observed ``current_a`` is stored
verbatim and passed through in :meth:`state` -- it is not filtered and has no
covariance entry. ``load_w`` is the total device load the battery sees, a
well-known engine input, so its channel carries a small observation noise and
converges tightly; the self-model reads this belief for endurance rather than
ground truth. See ``docs/model-cards/estimator-power-soc.md`` for the
covariance bound contract (BL-027 carries the full coupled EKF; this build
ships the gated linear-Gaussian baseline).
"""

from __future__ import annotations

import math

from ..types import Estimate, EstimatorHealth, Observation
from .health import ChannelSpec, ScalarChannel, build_health, parse_bounded

__all__ = ["PowerEstimator"]


_DEFAULT_INITIAL_SOC = 100.0
_DEFAULT_INITIAL_VOLTAGE = 14.4
_DEFAULT_SOC_SIGMA = 5.0
_DEFAULT_VOLTAGE_SIGMA = 0.5
_DEFAULT_SOC_PROCESS_SIGMA_PER_S = 0.05
_DEFAULT_VOLTAGE_PROCESS_SIGMA_PER_S = 0.01
_SOC_FALLBACK_SIGMA = 0.5
_VOLTAGE_FALLBACK_SIGMA = 0.05
# Load is a well-known input (the engine sets `load_w` from the committed draw),
# so the channel carries a small observation noise and tracks it tightly.
_DEFAULT_LOAD_W = 0.0
_DEFAULT_LOAD_SIGMA = 2.0
_DEFAULT_LOAD_PROCESS_SIGMA_PER_S = 0.1
_LOAD_FALLBACK_SIGMA = 0.25


class PowerEstimator:
    """Gated scalar Kalman filter over SoC and terminal voltage (BL-027)."""

    name: str = "power"

    def __init__(
        self,
        initial_soc: float = _DEFAULT_INITIAL_SOC,
        initial_voltage: float = _DEFAULT_INITIAL_VOLTAGE,
        soc_sigma: float = _DEFAULT_SOC_SIGMA,
        voltage_sigma: float = _DEFAULT_VOLTAGE_SIGMA,
        soc_process_sigma_per_s: float = _DEFAULT_SOC_PROCESS_SIGMA_PER_S,
        voltage_process_sigma_per_s: float = _DEFAULT_VOLTAGE_PROCESS_SIGMA_PER_S,
        initial_load_w: float = _DEFAULT_LOAD_W,
        load_sigma: float = _DEFAULT_LOAD_SIGMA,
        load_process_sigma_per_s: float = _DEFAULT_LOAD_PROCESS_SIGMA_PER_S,
    ) -> None:
        self._t = 0.0
        self._current = 0.0
        self._rejected = 0
        self._channels: dict[str, ScalarChannel] = {
            "soc_pct": ScalarChannel(
                float(initial_soc),
                float(soc_sigma) ** 2,
                ChannelSpec(process_var_per_s=float(soc_process_sigma_per_s) ** 2),
            ),
            "voltage_v": ScalarChannel(
                float(initial_voltage),
                float(voltage_sigma) ** 2,
                ChannelSpec(process_var_per_s=float(voltage_process_sigma_per_s) ** 2),
            ),
            "load_w": ScalarChannel(
                float(initial_load_w),
                float(load_sigma) ** 2,
                ChannelSpec(process_var_per_s=float(load_process_sigma_per_s) ** 2),
            ),
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

        soc = parse_bounded(payload.get("soc_pct"), 0.0, 100.0)
        if "soc_pct" in payload and soc is None:
            self._rejected += 1
        elif soc is not None:
            r = float(noise.get("soc_pct_sigma", _SOC_FALLBACK_SIGMA)) ** 2
            self._channels["soc_pct"].fuse(soc, r)

        voltage = parse_bounded(payload.get("voltage_v"), 0.0, math.inf)
        if "voltage_v" in payload and voltage is None:
            self._rejected += 1
        elif voltage is not None:
            r = float(noise.get("voltage_v_sigma", _VOLTAGE_FALLBACK_SIGMA)) ** 2
            self._channels["voltage_v"].fuse(voltage, r)

        load = parse_bounded(payload.get("load_w"), 0.0, math.inf)
        if "load_w" in payload and load is None:
            self._rejected += 1
        elif load is not None:
            r = float(noise.get("load_w_sigma", _LOAD_FALLBACK_SIGMA)) ** 2
            self._channels["load_w"].fuse(load, r)

        current = payload.get("current_a")
        if current is not None:
            try:
                value = float(current)
            except (TypeError, ValueError):
                value = self._current
            if math.isfinite(value):
                self._current = value

        try:
            ts = float(obs.ts_s)
        except (TypeError, ValueError):
            return
        if math.isfinite(ts) and ts >= 0.0:
            self._t = ts

    def health(self) -> EstimatorHealth:
        return build_health(self._channels, rejected_extra=self._rejected)

    def state(self) -> Estimate:
        soc = self._channels["soc_pct"]
        voltage = self._channels["voltage_v"]
        load = self._channels["load_w"]
        return Estimate(
            source=self.name,
            ts_s=self._t,
            point={
                "soc_pct": soc.value,
                "voltage_v": voltage.value,
                "current_a": self._current,
                "load_w": load.value,
            },
            covariance={
                "soc_pct": soc.var,
                "voltage_v": voltage.var,
                "load_w": load.var,
            },
            health=self.health(),
        )
