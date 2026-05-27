"""Compute load and electrical draw derived from a profile load curve.

Implements the :class:`~nous.subsystems.base.Subsystem` Protocol. The
compute subsystem turns a controller-supplied load fraction (0..100 %)
into a draw watts value via the piecewise-linear ``compute.load_curve``
in the hardware profile, with ``draw_w_idle`` / ``draw_w_load`` as the
endpoints when the curve is missing. The engine reads
:attr:`draw_w` each tick and feeds it into both the power subsystem
(electrical load) and the thermal subsystem (heat dissipation at the
junction), so a "spin up inference" command propagates through battery
endurance, junction temperature, and the FSM safety context together.

Controller seams:

* :meth:`set_load_pct` -- direct fractional steer (scenario YAML, BL-014).
* :meth:`set_inference_rate` -- helper that converts a token-per-second
  request into a load fraction via
  ``compute.inference_local.tok_per_s_p50``. Out-of-range rates clamp
  to the configured ceiling and set :attr:`saturated`.
* :meth:`set_thermal_throttle` -- the engine reports junction
  throttling so the subsystem can clip its delivered load to mimic
  hardware DVFS. The clipped value is preserved on
  :attr:`requested_load_pct` so the controller can see how much
  headroom was given back to thermal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

import numpy as np

from ..types import Observation

__all__ = ["ComputeSubsystem"]


_DEFAULT_DRAW_W_IDLE = 5.0
_DEFAULT_DRAW_W_LOAD = 25.0
_DEFAULT_LOAD_PCT = 5.0
_DEFAULT_TOK_PER_S_P50 = 0.0
_DEFAULT_ENERGY_J_PER_TOK = 0.0
_THROTTLE_CEIL_PCT = 60.0


class ComputeSubsystem:
    """Compute load, draw, and latency derived from profile curves (BL-007).

    State is two scalars: the requested load fraction (set by the
    controller) and the delivered load fraction (what the subsystem
    can actually push given thermal throttling). The delivered value
    drives :attr:`draw_w` through the profile's load curve.
    """

    name: str = "compute"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.profile = profile
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        cfg = dict(profile.get("compute") or {})
        self._draw_w_idle = float(cfg.get("draw_w_idle", _DEFAULT_DRAW_W_IDLE))
        self._draw_w_load = float(cfg.get("draw_w_load", _DEFAULT_DRAW_W_LOAD))
        self._load_curve = _parse_load_curve(
            cfg.get("load_curve"),
            idle_w=self._draw_w_idle,
            load_w=self._draw_w_load,
        )
        inference_cfg = dict(cfg.get("inference_local") or {})
        self._tok_per_s_p50 = float(
            inference_cfg.get("tok_per_s_p50", _DEFAULT_TOK_PER_S_P50)
        )
        self._energy_j_per_tok = float(
            inference_cfg.get("energy_j_per_tok", _DEFAULT_ENERGY_J_PER_TOK)
        )

        self._t = 0.0
        self._requested_load_pct = _DEFAULT_LOAD_PCT
        self._load_pct = _DEFAULT_LOAD_PCT
        self._throttle_ceiling_pct: float | None = None
        self._draw_w = self._interpolate_draw_w(self._load_pct)
        self._saturated = False

    def set_load_pct(self, load_pct: float) -> None:
        """Steer the target load fraction (clamped to [0, 100])."""
        self._requested_load_pct = _clamp_pct(load_pct)
        self._apply_throttle()

    def set_inference_rate(self, tok_per_s: float) -> None:
        """Translate a desired inference rate into a load fraction.

        Uses ``compute.inference_local.tok_per_s_p50`` as the 100 %-load
        reference. Rates above the reference clamp the load to 100 %
        and set :attr:`saturated`. If the profile does not declare a
        token rate, this method is a no-op.
        """
        if self._tok_per_s_p50 <= 0.0:
            return
        rate = max(0.0, float(tok_per_s))
        target = 100.0 * rate / self._tok_per_s_p50
        self._saturated = target > 100.0
        self.set_load_pct(target)

    def set_thermal_throttle(self, *, throttling: bool) -> None:
        """Cap delivered load when the thermal subsystem reports throttling."""
        self._throttle_ceiling_pct = _THROTTLE_CEIL_PCT if throttling else None
        self._apply_throttle()

    def clear_thermal_throttle(self) -> None:
        """Remove any thermal-throttle cap."""
        self.set_thermal_throttle(throttling=False)

    @property
    def load_pct(self) -> float:
        return self._load_pct

    @property
    def requested_load_pct(self) -> float:
        return self._requested_load_pct

    @property
    def draw_w(self) -> float:
        return self._draw_w

    @property
    def draw_w_idle(self) -> float:
        return self._draw_w_idle

    @property
    def draw_w_load(self) -> float:
        return self._draw_w_load

    @property
    def saturated(self) -> bool:
        """True when the requested inference rate exceeds the profile ceiling."""
        return self._saturated

    @property
    def throttled(self) -> bool:
        """True when delivered load is clipped below the request."""
        return self._load_pct < self._requested_load_pct - 1e-6

    @property
    def tok_per_s_capacity(self) -> float:
        """Profile-reported token-per-second capacity at p50 (0 if absent)."""
        return self._tok_per_s_p50

    def energy_for_tokens(self, n_tokens: float) -> float:
        """Joules of compute energy to emit ``n_tokens`` (0 if unmetered)."""
        return max(0.0, float(n_tokens)) * self._energy_j_per_tok

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "load_pct": self._load_pct,
            "requested_load_pct": self._requested_load_pct,
            "draw_w": self._draw_w,
            "draw_w_idle": self._draw_w_idle,
            "draw_w_load": self._draw_w_load,
            "throttled": self.throttled,
            "saturated": self._saturated,
            "tok_per_s_capacity": self._tok_per_s_p50,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={"load_pct": self._load_pct, "draw_w": self._draw_w},
            noise={"load_pct_sigma": 1.5, "draw_w_sigma": 0.5},
        )

    def _apply_throttle(self) -> None:
        if self._throttle_ceiling_pct is None:
            self._load_pct = self._requested_load_pct
        else:
            self._load_pct = min(
                self._requested_load_pct, self._throttle_ceiling_pct
            )
        self._draw_w = self._interpolate_draw_w(self._load_pct)

    def _interpolate_draw_w(self, load_pct: float) -> float:
        return _piecewise_linear(self._load_curve, _clamp_pct(load_pct))


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, float(value)))


def _parse_load_curve(
    raw: Any, *, idle_w: float, load_w: float
) -> list[tuple[float, float]]:
    """Coerce a profile load curve into a sorted list of (load_pct, draw_w)."""
    points: list[tuple[float, float]] = []
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        for entry in raw:
            if not isinstance(entry, Mapping):
                continue
            lp = entry.get("load_pct")
            dw = entry.get("draw_w")
            if lp is None or dw is None:
                continue
            try:
                points.append((float(lp), float(dw)))
            except (TypeError, ValueError):
                continue
    if not points:
        points = [(0.0, idle_w), (100.0, load_w)]
    points.sort(key=lambda p: p[0])
    return points


def _piecewise_linear(points: Sequence[tuple[float, float]], x: float) -> float:
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return points[-1][1]
