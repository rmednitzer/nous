# ADR 0078: EO/IR terrain line-of-sight masking

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0072, ADR 0077

## Context

ADR 0077 shipped the EO/IR payload as a clear-field detection-range envelope and
explicitly deferred terrain line-of-sight masking of a configured target as a
named fast-follow ("a scenario needs detection against a specific target over
terrain, then the line-of-sight masking lands, reusing the `WorldSource`
`path_profile`"). This ADR lands that half. It is the marquee tie-in to the world
arc (ADR 0072): the envelope says how far the payload could reach in the clear,
but a ridge between the platform and a target occludes it regardless of range.

The geometry already exists in the repository. The comms propagation path (BL-089)
samples the terrain between the device and a peer with
`TerrainModel.path_profile` and runs a Bullington multi-edge diffraction over it;
the first thing that computation does is a geometric clearance test (is any
interior terrain point above the straight line between the endpoints). For an
optical sensor the Fresnel zone is negligible, so occlusion is exactly that
geometric test, with no diffraction physics to model.

## Decision

Give `EoirSubsystem` two optional constructor seams, `terrain: WorldSource | None`
and `position_fn: Callable[[], tuple[float, float, float]] | None`, mirroring how
`CommsSubsystem` is wired, plus `set_target(bearing_deg, range_m, height_m)` and
`clear_target()`. When a target is set and both seams are present, the subsystem
projects the target latitude and longitude from the platform position (an inline
equirectangular step, the idiom already repeated in `position.py` and
`position_ekf.py`), samples `terrain.path_profile`, and evaluates whether the
sightline is clear. It reports `target_visible`, the slant range
(`propagation.slant_range_m`), and a per-band `detection_confidence`
(`visible ? clamp(1 - slant / R_eff_band, 0, 1) : 0`), surfaced in `truth()` and,
when a target is set, in the `eoir_status` tool.

The clearance predicate is extracted from the comms path rather than duplicated.
`bullington_diffraction_db` already returned zero loss for a path whose terrain
stays at or below the line of sight; that early-return geometry becomes a new
public `propagation.los_clear(profile, tx_height_m, rx_height_m) -> bool`, and
`bullington` calls it for its own early return. The behaviour is identical (the
`test_bullington_*` suite guards it) and the EO/IR subsystem imports the same
predicate, so there is one source of truth for "is the path clear".

With no target set (the default), the LOS fields are inert (`target_set=False`,
the rest `None`) and `path_profile` is never sampled, so the envelope behaviour
ships unchanged and at zero added per-tick cost. The engine passes
`terrain=self.terrain` and the position closure into the EO/IR subsystem in both
construction and `reload_profile`, capturing the new generation's position and
terrain on reload (the same discipline as the ambient closure).

## Consequences

A controller can now ask a target-specific question, "can I see the vehicle at
bearing 090, range 4 km", and get an honest answer that folds terrain occlusion
together with the atmospheric, thermal-contrast, and calibration envelope. A
target behind a ridge reads `target_visible=False` with zero confidence even when
the clear-field range would reach it; a target in the open beyond the envelope
reads visible but zero confidence. The two effects compose, which is the
cross-subsystem legibility the world arc exists to provide.

The LOS overlay is a pure geometric function of position and terrain with no RNG,
so it does not touch the seeded-determinism guarantee, and it is a deterministic
overlay on truth rather than a filtered quantity, so the estimator is unchanged.
The `los_clear` extraction touches the comms-critical `propagation.py`, but only
by naming an existing predicate; the comms link-budget behaviour is byte-identical
and its test suite proves it.

The model remains an envelope: a single target at a time, a straight-line
clearance test over the sampled profile (no earth-curvature or refraction term, as
in the comms path), and a confidence that is a geometric range fraction, not a
probability of detection. `LIMITATIONS.md` L19 and the conformance note record
this.

## Alternatives considered and rejected

- Duplicating the clearance math into the subsystem. Rejected: it would fork a
  predicate that must stay consistent with the comms terrain path. Extracting
  `los_clear` keeps one source of truth.
- Reusing `bullington_diffraction_db` at an optical frequency and testing for a
  non-zero loss. Rejected: passing an optical frequency to a radio-diffraction
  function is semantically wrong and the Fresnel term is meaningless at that
  wavelength; the geometric `los_clear` is the honest predicate.
- A full multi-target track list. Rejected for scope: one target answers the
  controller's question and keeps the subsystem an envelope, not a tracker.

## Revisit triggers

- A scenario needs several simultaneous targets (then a target list, each with its
  own LOS verdict and confidence).
- Earth curvature or atmospheric refraction matters at the ranges in use (then the
  comms path and this one share a corrected-profile helper).
- The self-model should reason about target detectability (then `perception_range`
  or a target-detection capability folds `detection_confidence` in).
