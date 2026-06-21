"""EO/IR thermo-optical payload: detection-range capability envelope (BL-055).

The platform carries an electro-optical (visible) plus long-wave infrared sensor,
the perception input the onboard inference runs on. The twin does not render
imagery; it models the sensing *capability* a controller has to reason about: how
far the payload can detect a target right now, per band, and which physical effect
has shortened that range.

The effective detection range of each band is a bounded product of a clear-air
reference range and three unit-interval factors: atmospheric extinction (a
Koschmieder meteorological-range cap that tightens with humidity and an obscurant
level), a band signal factor (infrared thermal contrast, which collapses at
thermal crossover when the background warms to the target temperature; electro-
optical illumination, which falls off at night), and a calibration-health factor
that drifts down as the focal-plane non-uniformity correction ages and recovers on
a recalibration. A degraded calibration both shortens the range and widens the
reported measurement sigma, so the paired estimator leans harder on its prior.

The Johnson criteria turn each detection range into recognition and identification
ranges by the cycle ratios. Ambient temperature and humidity are read live from the
environmental sensor pack through an injected closure (the seam the engine wires),
so an air-conditioned room, a humid dusk, or a smoke screen all propagate into the
perception envelope the controller sees.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np

from ..types import Observation
from .propagation import los_clear, slant_range_m
from .terrain import WorldSource

__all__ = ["EoirSubsystem"]

AmbientFn = Callable[[], tuple[float, float]]
PositionFn = Callable[[], tuple[float, float, float]]

_DEFAULT_EO_R0_M = 12000.0
_DEFAULT_IR_R0_M = 8000.0
_DEFAULT_TARGET_C = 32.0
_DEFAULT_DT_REF_C = 10.0
_DEFAULT_K_REC = 3.0
_DEFAULT_K_ID = 6.0
_DEFAULT_EO_RANGE_SIGMA = 200.0
_DEFAULT_IR_RANGE_SIGMA = 150.0
_DEFAULT_CAL_FLOOR = 0.3
_DEFAULT_CAL_DRIFT_PER_S = 0.002
# A positive floor on the sigma divisor: a profile may set cal_floor to 0, and a
# fully decalibrated payload (cal_factor -> 0) must inflate the sigma, not divide
# by zero on the tick / tool path.
_MIN_CAL_DIVISOR = 1e-3
# Koschmieder constant: meteorological range V (km) = 3.912 / extinction (1/km)
# at the 2 percent contrast threshold.
_KOSCHMIEDER = 3.912
_HUMIDITY_KNEE_PCT = 50.0
_DEFAULT_EO_BASE_EXT = 0.1
_DEFAULT_IR_BASE_EXT = 0.05
_DEFAULT_EO_HUM_EXT = 0.3
_DEFAULT_IR_HUM_EXT = 0.1
_DEFAULT_EO_OBSC_EXT = 3.0
_DEFAULT_IR_OBSC_EXT = 1.5
_NOMINAL_AMBIENT_C = 22.0
_NOMINAL_HUMIDITY_PCT = 50.0
# WGS84-ish metres per degree of latitude, matching position.py / position_ekf.py.
_METERS_PER_DEG_LAT = 111_320.0
_TERRAIN_SAMPLES = 24


class EoirSubsystem:
    """Electro-optical + infrared payload modelled as a detection-range envelope."""

    name: str = "eoir"

    def __init__(
        self,
        profile: Mapping[str, Any],
        *,
        rng: np.random.Generator | None = None,
        ambient_fn: AmbientFn | None = None,
        terrain: WorldSource | None = None,
        position_fn: PositionFn | None = None,
    ) -> None:
        self._rng = rng  # ADR 0019 follow-up: engine RNG seam
        self._ambient_fn = ambient_fn
        self._terrain = terrain
        self._position_fn = position_fn
        self.profile = profile
        cfg = dict(profile.get("eoir") or {})
        self._eo_r0 = max(0.0, float(cfg.get("eo_r0_m", _DEFAULT_EO_R0_M)))
        self._ir_r0 = max(0.0, float(cfg.get("ir_r0_m", _DEFAULT_IR_R0_M)))
        self._target_c = float(cfg.get("target_c", _DEFAULT_TARGET_C))
        self._dt_ref_c = max(1e-6, float(cfg.get("contrast_dt_ref_c", _DEFAULT_DT_REF_C)))
        self._k_rec = max(1.0, float(cfg.get("johnson_k_rec", _DEFAULT_K_REC)))
        self._k_id = max(1.0, float(cfg.get("johnson_k_id", _DEFAULT_K_ID)))
        self._eo_sigma = max(0.0, float(cfg.get("eo_range_sigma_m", _DEFAULT_EO_RANGE_SIGMA)))
        self._ir_sigma = max(0.0, float(cfg.get("ir_range_sigma_m", _DEFAULT_IR_RANGE_SIGMA)))
        self._cal_floor = _clamp01(float(cfg.get("cal_floor", _DEFAULT_CAL_FLOOR)))
        self._cal_drift = max(0.0, float(cfg.get("cal_drift_per_s", _DEFAULT_CAL_DRIFT_PER_S)))
        self._eo_base_ext = max(1e-6, float(cfg.get("eo_base_ext_per_km", _DEFAULT_EO_BASE_EXT)))
        self._ir_base_ext = max(1e-6, float(cfg.get("ir_base_ext_per_km", _DEFAULT_IR_BASE_EXT)))
        self._eo_hum_ext = max(0.0, float(cfg.get("eo_humidity_ext_per_km", _DEFAULT_EO_HUM_EXT)))
        self._ir_hum_ext = max(0.0, float(cfg.get("ir_humidity_ext_per_km", _DEFAULT_IR_HUM_EXT)))
        self._eo_obsc_ext = max(
            0.0, float(cfg.get("eo_obscurant_ext_per_km", _DEFAULT_EO_OBSC_EXT))
        )
        self._ir_obsc_ext = max(
            0.0, float(cfg.get("ir_obscurant_ext_per_km", _DEFAULT_IR_OBSC_EXT))
        )
        self._obscurant = _clamp01(float(cfg.get("obscurant_default", 0.0)))
        self._illumination = _clamp01(float(cfg.get("illumination_default", 1.0)))
        self._cal_factor = 1.0
        self._t = 0.0
        self._eo_range_m = self._eo_r0
        self._ir_range_m = self._ir_r0
        self._atm_eo = 1.0
        self._atm_ir = 1.0
        self._ir_contrast = 1.0
        self._eo_illum = 1.0
        self._target: tuple[float, float, float] | None = None
        self._target_visible: bool | None = None
        self._target_slant_m: float | None = None
        self._eo_conf: float | None = None
        self._ir_conf: float | None = None
        self._recompute()

    def set_obscurant(self, level: float) -> None:
        """Battlefield obscurant in [0, 1]: 0 clear, 1 heavy fog / dust / smoke."""
        self._obscurant = _clamp01(float(level))

    def set_illumination(self, fraction: float) -> None:
        """EO scene illumination in [0, 1]: 1 full daylight, 0 unlit night."""
        self._illumination = _clamp01(float(fraction))

    def recalibrate(self) -> None:
        """Restore the focal-plane calibration health to full."""
        self._cal_factor = 1.0
        self._recompute()

    def set_target(self, bearing_deg: float, range_m: float, height_m: float = 0.0) -> None:
        """Place a target at a bearing (deg CW from north), ground range, and height.

        With a target set, and the terrain + position seams wired, the subsystem
        masks detection when a ridge occludes the sightline (target_visible) and
        reports a per-band detection_confidence. Inert without terrain/position.
        """
        self._target = (float(bearing_deg), max(0.0, float(range_m)), float(height_m))
        self._recompute()

    def clear_target(self) -> None:
        """Remove the configured target; the subsystem reports the envelope only."""
        self._target = None
        self._recompute()

    @property
    def target_visible(self) -> bool | None:
        return self._target_visible

    @property
    def target_slant_m(self) -> float | None:
        return self._target_slant_m

    @property
    def eo_range_m(self) -> float:
        return self._eo_range_m

    @property
    def ir_range_m(self) -> float:
        return self._ir_range_m

    @property
    def cal_factor(self) -> float:
        return self._cal_factor

    @property
    def obscurant(self) -> float:
        return self._obscurant

    @property
    def illumination(self) -> float:
        return self._illumination

    def step(self, dt: float) -> None:
        if dt <= 0.0:
            return
        self._t += dt
        if self._rng is not None and self._cal_drift > 0.0:
            # Non-uniformity correction ages monotonically until a recalibration;
            # the half-normal step keeps the walk one-directional toward the floor.
            drift = abs(float(self._rng.normal(0.0, self._cal_drift * math.sqrt(dt))))
            self._cal_factor = max(self._cal_floor, self._cal_factor - drift)
        self._recompute()

    def _ambient(self) -> tuple[float, float]:
        if self._ambient_fn is None:
            return _NOMINAL_AMBIENT_C, _NOMINAL_HUMIDITY_PCT
        temp_c, humidity_pct = self._ambient_fn()
        return float(temp_c), float(humidity_pct)

    def _recompute(self) -> None:
        ambient_c, humidity_pct = self._ambient()
        hum_excess = max(0.0, humidity_pct - _HUMIDITY_KNEE_PCT) / (100.0 - _HUMIDITY_KNEE_PCT)
        eo_ext = (
            self._eo_base_ext + self._eo_hum_ext * hum_excess + self._eo_obsc_ext * self._obscurant
        )
        ir_ext = (
            self._ir_base_ext + self._ir_hum_ext * hum_excess + self._ir_obsc_ext * self._obscurant
        )
        self._atm_eo = _atm_factor(eo_ext, self._eo_r0)
        self._atm_ir = _atm_factor(ir_ext, self._ir_r0)
        self._ir_contrast = _clamp01(abs(self._target_c - ambient_c) / self._dt_ref_c)
        self._eo_illum = _clamp01(self._illumination)
        self._eo_range_m = self._eo_r0 * self._atm_eo * self._eo_illum * self._cal_factor
        self._ir_range_m = self._ir_r0 * self._atm_ir * self._ir_contrast * self._cal_factor
        self._evaluate_target()

    def _evaluate_target(self) -> None:
        if self._target is None or self._terrain is None or self._position_fn is None:
            self._target_visible = None
            self._target_slant_m = None
            self._eo_conf = None
            self._ir_conf = None
            return
        plat_lat, plat_lon, plat_alt = self._position_fn()
        bearing_deg, range_m, height_m = self._target
        brg = math.radians(bearing_deg)
        cos_lat = max(1e-6, math.cos(math.radians(plat_lat)))
        tgt_lat = plat_lat + (range_m * math.cos(brg)) / _METERS_PER_DEG_LAT
        tgt_lon = plat_lon + (range_m * math.sin(brg)) / (_METERS_PER_DEG_LAT * cos_lat)
        tgt_alt = self._terrain.elevation(tgt_lat, tgt_lon) + height_m
        profile = self._terrain.path_profile(
            plat_lat, plat_lon, tgt_lat, tgt_lon, _TERRAIN_SAMPLES
        )
        self._target_visible = los_clear(profile, plat_alt, tgt_alt)
        self._target_slant_m = slant_range_m(
            plat_lat, plat_lon, plat_alt, tgt_lat, tgt_lon, tgt_alt
        )
        self._eo_conf = self._detection_confidence(self._eo_range_m)
        self._ir_conf = self._detection_confidence(self._ir_range_m)

    def _detection_confidence(self, band_range_m: float) -> float:
        if not self._target_visible or band_range_m <= 0.0 or self._target_slant_m is None:
            return 0.0
        return _clamp01(1.0 - self._target_slant_m / band_range_m)

    def truth(self) -> Mapping[str, Any]:
        return {
            "eo_range_m": self._eo_range_m,
            "ir_range_m": self._ir_range_m,
            "eo_recognition_m": self._eo_range_m / self._k_rec,
            "eo_identification_m": self._eo_range_m / self._k_id,
            "ir_recognition_m": self._ir_range_m / self._k_rec,
            "ir_identification_m": self._ir_range_m / self._k_id,
            "atm_factor_eo": self._atm_eo,
            "atm_factor_ir": self._atm_ir,
            "ir_contrast_factor": self._ir_contrast,
            "eo_illum_factor": self._eo_illum,
            "cal_factor": self._cal_factor,
            "obscurant": self._obscurant,
            "illumination": self._illumination,
            "target_set": self._target is not None,
            "target_visible": self._target_visible,
            "target_slant_m": self._target_slant_m,
            "eo_detection_confidence": self._eo_conf,
            "ir_detection_confidence": self._ir_conf,
            "t": self._t,
        }

    def sensor_obs(self) -> Observation:
        # A degraded calibration is reported as a wider range sigma, so the
        # estimator down-weights an untrustworthy payload toward its prior.
        cal = max(self._cal_floor, self._cal_factor, _MIN_CAL_DIVISOR)
        return Observation(
            source=self.name,
            ts_s=self._t,
            payload={
                "eo_range_m": self._eo_range_m,
                "ir_range_m": self._ir_range_m,
            },
            noise={
                "eo_range_m_sigma": self._eo_sigma / cal,
                "ir_range_m_sigma": self._ir_sigma / cal,
            },
        )


def _atm_factor(extinction_per_km: float, r0_m: float) -> float:
    if r0_m <= 0.0:
        return 1.0
    visibility_m = (_KOSCHMIEDER / extinction_per_km) * 1000.0
    return _clamp01(visibility_m / r0_m)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
