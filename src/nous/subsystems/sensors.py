"""Environmental sensor pack: ambient ground truth + noise envelope (BL-009).

The simulator carries ambient temperature, relative humidity, and
barometric pressure as ground truth on this subsystem. The engine
reads :attr:`temp_c` each tick to drive the thermal subsystem's
ambient input, which means the controller can simulate "the operator
walked into an air-conditioned room" or "the patrol crossed the snow
line" through a single ``set_temp_c`` call and watch the change
propagate through enclosure cooling, battery cell temperature, and
the FSM's thermal-headroom guard.

Profile fields under ``sensors.environmental``:

* ``temp_c_default`` / ``humidity_pct_default`` / ``baro_kpa_default``
  -- starting values; if absent we fall back to comfortable room
  conditions.
* ``temp_c_sigma`` / ``humidity_pct_sigma`` / ``baro_kpa_sigma`` --
  advertised on every observation so the environmental Kalman sizes
  its gain against the appliance's actual sensor spec sheet.

Controller seams: :meth:`set_temp_c`, :meth:`set_humidity_pct`,
:meth:`set_baro_kpa` accept any finite scalar (humidity clamps to
``[0, 100]``; pressure to ``[10, 200]`` kPa to keep crazy injections
from poisoning downstream consumers).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from ..types import Observation

__all__ = ["SensorsSubsystem"]


_DEFAULT_TEMP_C = 22.0
_DEFAULT_HUMIDITY_PCT = 50.0
_DEFAULT_BARO_KPA = 101.3
_DEFAULT_TEMP_SIGMA = 0.2
_DEFAULT_HUMIDITY_SIGMA = 1.0
_DEFAULT_BARO_SIGMA = 0.1
_BARO_KPA_MIN = 10.0
_BARO_KPA_MAX = 200.0


class SensorsSubsystem:
    """Environmental sensors aggregated through a single subsystem."""

    name: str = "sensors"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        self.profile = profile
        cfg = dict((profile.get("sensors") or {}).get("environmental") or {})
        thermal_cfg = profile.get("thermal") or {}
        seeded_temp = cfg.get(
            "temp_c_default", thermal_cfg.get("ambient_c_default", _DEFAULT_TEMP_C)
        )
        self._temp_c = float(seeded_temp)
        self._humidity_pct = _clamp_pct(
            float(cfg.get("humidity_pct_default", _DEFAULT_HUMIDITY_PCT))
        )
        self._baro_kpa = _clamp_baro(
            float(cfg.get("baro_kpa_default", _DEFAULT_BARO_KPA))
        )
        self._temp_sigma = float(cfg.get("temp_c_sigma", _DEFAULT_TEMP_SIGMA))
        self._humidity_sigma = float(
            cfg.get("humidity_pct_sigma", _DEFAULT_HUMIDITY_SIGMA)
        )
        self._baro_sigma = float(cfg.get("baro_kpa_sigma", _DEFAULT_BARO_SIGMA))
        self._t = 0.0

    def set_temp_c(self, temp_c: float) -> None:
        self._temp_c = float(temp_c)

    def set_humidity_pct(self, humidity_pct: float) -> None:
        self._humidity_pct = _clamp_pct(float(humidity_pct))

    def set_baro_kpa(self, baro_kpa: float) -> None:
        self._baro_kpa = _clamp_baro(float(baro_kpa))

    @property
    def temp_c(self) -> float:
        return self._temp_c

    @property
    def humidity_pct(self) -> float:
        return self._humidity_pct

    @property
    def baro_kpa(self) -> float:
        return self._baro_kpa

    @property
    def temp_sigma(self) -> float:
        return self._temp_sigma

    @property
    def humidity_sigma(self) -> float:
        return self._humidity_sigma

    @property
    def baro_sigma(self) -> float:
        return self._baro_sigma

    def step(self, dt: float) -> None:
        if dt > 0.0:
            self._t += dt

    def truth(self) -> Mapping[str, Any]:
        return {
            "temp_c": self._temp_c,
            "humidity_pct": self._humidity_pct,
            "baro_kpa": self._baro_kpa,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "temp_c": self._temp_c,
                "humidity_pct": self._humidity_pct,
                "baro_kpa": self._baro_kpa,
            },
            noise={
                "temp_c_sigma": self._temp_sigma,
                "humidity_pct_sigma": self._humidity_sigma,
                "baro_kpa_sigma": self._baro_sigma,
            },
        )


def _clamp_pct(value: float) -> float:
    return max(0.0, min(100.0, value))


def _clamp_baro(value: float) -> float:
    return max(_BARO_KPA_MIN, min(_BARO_KPA_MAX, value))
