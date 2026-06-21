# Model card: EO/IR thermo-optical subsystem

**Module:** `src/nous/subsystems/eoir.py`

**Backlog:** BL-055

## Scope

Models an electro-optical (visible) plus long-wave infrared payload as a
**detection-range capability envelope**, not as imagery. It is authoritative for
the per-band effective detection range, the Johnson-criteria recognition and
identification ranges derived from it, and the factor breakdown that explains a
shortened range. This is the perception capability a controller acts on: how far
each band can reach right now, and why.

Each band's effective range is a bounded product of a clear-air reference range
and three unit-interval factors: atmospheric extinction (a Koschmieder
meteorological-range cap tightening with humidity and an obscurant level),
a signal factor (infrared thermal contrast, collapsing at thermal crossover;
electro-optical illumination, falling off at night), and a calibration-health
factor. The calibration factor is the only internal dynamic state: it drifts down
on the engine RNG seam (focal-plane non-uniformity ageing) and recovers on a
recalibration. Ambient temperature and humidity are read live from the
environmental sensor pack through an injected closure, so an environmental change
propagates into the perception envelope through the tick loop. See
`docs/conformance/eoir.md` for the Johnson, Koschmieder, and thermal-contrast
sources.

## Inputs

| Seam | Notes |
|------|-------|
| `set_obscurant` | Battlefield obscurant in [0, 1]: 0 clear, 1 heavy fog / dust / smoke |
| `set_illumination` | EO scene illumination in [0, 1]: 1 daylight, 0 unlit night |
| `recalibrate` | Restores calibration health to full |
| `set_target` / `clear_target` | Place / remove a target at `(bearing_deg, range_m, height_m)` for line-of-sight masking |
| `ambient_fn` | Engine closure returning live `(temp_c, humidity_pct)`; falls back to a nominal ambient when absent |
| `terrain` / `position_fn` | Optional `WorldSource` + platform-position closure; enable terrain LOS masking of the target (inert when absent) |

## State (truth())

| Field | Units | Notes |
|-------|-------|-------|
| `eo_range_m` / `ir_range_m` | m | Effective detection range per band |
| `eo_recognition_m` / `ir_recognition_m` | m | Detection range / `k_rec` |
| `eo_identification_m` / `ir_identification_m` | m | Detection range / `k_id` |
| `atm_factor_eo` / `atm_factor_ir` | -- | Atmospheric extinction factor in (0, 1] |
| `ir_contrast_factor` | -- | Thermal contrast in [0, 1]; 0 at crossover |
| `eo_illum_factor` | -- | Illumination in [0, 1] |
| `cal_factor` | -- | Calibration health in (0, 1] |
| `obscurant` / `illumination` | -- | Current scene inputs |
| `target_set` / `target_visible` | -- | Whether a target is configured and, if terrain+position are wired, whether the sightline is clear (else `None`) |
| `target_slant_m` | m | Slant range to the configured target |
| `eo_detection_confidence` / `ir_detection_confidence` | -- | Per-band `visible ? clamp(1 - slant / R_eff, 0, 1) : 0` |

## Outputs (sensor_obs())

| Field | Units | Sigma |
|-------|-------|-------|
| `eo_range_m` | m | `eo_range_sigma_m` / `cal_factor` (widens as calibration drifts) |
| `ir_range_m` | m | `ir_range_sigma_m` / `cal_factor` |

## Profile fields

```yaml
eoir:
  eo_r0_m: 12000            # clear-air EO reference detection range
  ir_r0_m: 8000             # clear-air IR reference detection range
  target_c: 32              # nominal target surface temperature
  contrast_dt_ref_c: 10     # thermal-contrast normalisation
  johnson_k_rec: 3          # recognition cycle ratio
  johnson_k_id: 6           # identification cycle ratio
  eo_range_sigma_m: 200     # base measurement sigma (scaled by 1 / cal_factor)
  ir_range_sigma_m: 150
  cal_floor: 0.3            # calibration health floor
  cal_drift_per_s: 0.002    # calibration random-walk rate (needs the RNG seam)
  obscurant_default: 0.0
  illumination_default: 1.0
  # per-band extinction coefficients (1/km) for the Koschmieder cap
  eo_base_ext_per_km: 0.1
  ir_base_ext_per_km: 0.05
  eo_humidity_ext_per_km: 0.3
  ir_humidity_ext_per_km: 0.1
  eo_obscurant_ext_per_km: 3.0
  ir_obscurant_ext_per_km: 1.5
```

## Known limitations

- An envelope, not a detector. There is no imagery, no per-object track, and no
  learned recognition; the Johnson DRI ranges are a deterministic geometric
  scaling of the detection range, not a probability of identification.
- Single target temperature. Thermal contrast is computed against one profile
  target temperature, not a background distribution or a per-target signature, so
  crossover is a single sharp transition rather than a scene-dependent band.
- Terrain line-of-sight masking (ADR 0078) covers one target at a time with a
  straight-line clearance test over the sampled profile (no earth curvature or
  refraction term); `detection_confidence` is a geometric range fraction, not a
  probability of detection.
- The atmospheric model is a Koschmieder meteorological-range cap, not a spectral
  transmittance calculation; it captures the haze/fog/obscurant trend, not band
  fine structure within the LWIR window.
