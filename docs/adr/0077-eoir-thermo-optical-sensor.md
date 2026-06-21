# ADR 0077: EO/IR thermo-optical sensor as a detection-range envelope

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0045, ADR 0072

## Context

The moving-platform arc (ADR 0072 terrain, ADR 0073/0076 the GNSS/INS EKF, ADR
0075 the PMU) modelled where the appliance is and how it is powered, but not what
it perceives. An edge-AI inference appliance on a moving platform runs its models
on an electro-optical and infrared payload, and the first thing a controller has
to reason about is that payload's reach: how far it can detect, recognize, and
identify a target right now, and which physical effect has shortened that reach.
BL-055 is that subsystem.

The twin does not render imagery, and modelling pixels would be both out of scope
and misleading about fidelity. What it can model honestly, and what a controller
actually acts on, is the sensing *capability*: a per-band effective detection
range and the calibrated belief about it. That framing also lets the payload
reuse the seams already built, the environmental sensor pack for ambient
conditions and the terrain `WorldSource` for the line-of-sight follow-on.

## Decision

Add an EO/IR subsystem (`subsystems/eoir.py`, `EoirSubsystem`) and a paired
estimator (`estimators/eoir.py`, `EoirKalman`), and expose them through a new T0
`eoir_status` read tool.

The subsystem tracks an effective detection range per band as a bounded product
`R_eff = R0 x atm_factor x signal_factor x cal_factor`. The atmospheric factor is
a Koschmieder meteorological-range cap that tightens with relative humidity and an
obscurant level, with a smaller humidity coupling on the infrared band so it
penetrates haze better than the visible band. The signal factor is the infrared
thermal contrast (which collapses to zero at thermal crossover, when the
background warms to the target temperature) and the electro-optical illumination
(which falls off at night). The calibration factor is the focal-plane
non-uniformity health, carried as an internal state that drifts down on the
ADR 0019 RNG seam and recovers on a `recalibrate()` call; a degraded calibration
both shortens the range and widens the reported measurement sigma, so the
estimator leans harder on its prior. Ambient temperature and humidity are read
live from the environmental sensor pack through an injected closure, the same
seam pattern the comms subsystem uses for position and terrain. The Johnson
criteria turn each detection range into recognition and identification ranges by
the cycle ratios, derived in `truth()` rather than separately filtered.

`EoirKalman` is a two-channel gated scalar Kalman over the two band ranges, a
direct reuse of the `EnvironmentalKalman` shape (the ADR 0045 `ScalarChannel`
primitive, the `parse_bounded` input gate, `build_health`). The engine constructs
the subsystem after the sensor pack, steps it after the sensors have settled, and
folds its observation into the estimator alongside the other channel filters. The
estimator satisfies the unchanged `predict / update / state` Protocol, the profile
section is free-form under the existing `ProfileModel` (`extra="allow"`), and the
only governance-boundary touch is the additive `eoir_status` entry in the
`policy.py` read-only set, which this ADR authorises.

## Consequences

A controller gains an honest perception envelope: two band ranges with calibrated
covariance, the recognition and identification ranges, and the breakdown of which
factor (haze, fog, thermal crossover, darkness, calibration drift) is shortening
each band. Because the atmospheric and contrast factors read the live sensor pack,
an environmental change the controller injects, an air-conditioned room, a humid
dusk, a smoke screen, propagates into the perception envelope through the same
tick loop, which is the cross-subsystem legibility the twin exists to provide.

The cost is one more subsystem and estimator in the tick and the post-tick finite
guard, both trivial at the tick budget. The model is an envelope, not a detector:
it carries no imagery, no per-object track, and no learned recognition model, and
it says so in its model card and LIMITATIONS. With no `eoir` profile section the
subsystem reproduces clear-air reference ranges deterministically, so the change
is additive and inert by default.

## Alternatives considered and rejected

- Modelling imagery or a learned detector. Rejected: it would misrepresent the
  twin's fidelity and is out of v0.1 scope, like the inference-local mock. The
  capability envelope is the legible, defensible thing.
- A single fused "perception quality" scalar. Rejected: the EO and IR bands
  degrade under different physics (illumination versus thermal contrast, and
  different atmospheric coupling), so collapsing them would hide exactly the
  band-selection decision a controller needs.
- Folding the terrain line-of-sight masking into this increment. Deferred to a
  named fast-follow to keep the PR reviewable: it needs a target track and the
  position projection, and the envelope plus its couplings is already a complete,
  testable capability. The constructor seam is shaped so the follow-on is additive.
- A self-model `perception_range` capability in this increment. Deferred: the
  self-model is a higher-blast surface (BL-061 was its own increment); the
  subsystem, estimator, and tool stand on their own first.

## Revisit triggers

- A scenario needs detection against a specific target over terrain (then the
  line-of-sight masking lands, reusing the `WorldSource` `path_profile`).
- The self-model should answer "can I identify a target at range X" (then a
  `perception_range` capability folds the EO/IR estimate into `assess` /
  `situation`).
- The single-target-temperature contrast model proves too coarse (then a
  background-temperature distribution or a per-scenario target signature).
