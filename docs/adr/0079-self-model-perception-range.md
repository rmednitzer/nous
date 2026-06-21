# ADR 0079: perception_range self-model capability

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0035, ADR 0038, ADR 0077

## Context

ADR 0077 shipped the EO/IR estimator and named, as its last fast-follow, a
self-model `perception_range` capability that folds the EO/IR belief into
`assess` / `situation` so the controller can ask "how far can I perceive right
now" alongside endurance, thermal headroom, and inference capacity. With the
envelope (ADR 0077) and terrain line-of-sight (ADR 0078) merged, this ADR lands
that capability and closes BL-055.

The self-model already has the shape: `assess` (ADR 0010) reads each estimator's
posterior and emits a `Capability` with calibrated `p5 / p50 / p95` quantiles via
the Monte Carlo mapping (ADR 0035), and `situation` (ADR 0038) fuses those claims
with provenance, staleness, the FSM posture, the safety posture, and ranked
advice. The capabilities are wired as explicit named fields rather than a
registry, so a new one is added the same way the three existing ones are.

## Decision

Add a fourth capability, `perception_range_m`, computed from the EO/IR Kalman
posterior. The headline value is the best band, `max(eo_range, ir_range)`: the
electro-optical band reaches furthest by day, the infrared band by night or
through smoke, so the better of the two is the honest answer to how far the
device can perceive. The Monte Carlo branch samples both bands from the EO/IR
posterior and takes the per-sample maximum before quantiling, so the band
reflects the nonlinear best-of-two rather than one channel; the Gaussian fallback
uses the dominant band's spread. The claim names `eoir` and `sensors` as its
drivers (the sensor pack supplies the ambient that sets the atmospheric and
thermal-contrast factors).

The capability flows through every self-model surface the same way the existing
three do: a named field on `Assessment` with its `assess` computation and its
`_empty_assessment` stub; `explain` lists it; `situation` adds `eoir` to the
estimator-attribute map for staleness, iterates it, gives it a status keyed on
the conservative `p5` against metre floors, and emits a recommendation that names
the limiting factor for the best band (atmospheric obscuration, illumination, or
thermal contrast, picked from the band that actually sets the range, not the
global minimum); the `self_model_assess` and `self_model_situation` tools surface
it without further wiring; the engine caches its point in `last_capabilities`;
and `viability` gains a `perception_range_m` requirement, exposed as a
`self_model_viability` parameter, so a controller can gate a task on "detect at
range X".

This is additive and surfaces no new MCP tool, so there is no `policy.py` change:
the existing T0 `self_model_*` reads carry the new capability. The estimator and
the EO/IR subsystem are untouched; the capability is a read-side projection of the
belief they already publish.

## Consequences

A controller now reads perception reach as a first-class capability with an
uncertainty band, provenance, and staleness, and can ask whether a detection task
is feasible. Under degradation the situation read names the cause: heavy fog
collapses the band and the recommendation says "atmospheric obscuration"; a warm
background that crosses the infrared target temperature leaves the electro-optical
band as the best and is reported against it. The best-band framing keeps one
legible number while the explanation and the limiter name preserve which band and
which physical effect are in play.

The cost is the per-capability wiring touched in several files (the named-field
pattern the self-model deliberately uses), each change small and additive. The
capability is a deterministic-plus-seeded-Monte-Carlo projection of the EO/IR
posterior; it adds no new estimator and no new failure mode beyond the EO/IR
belief it reads. The best-band maximum is a coarse fusion (a controller that needs
per-band reach still reads `eoir_status`), and the status floors are advisory
heuristics tuned to the reference profile, like the other capabilities' floors.

## Alternatives considered and rejected

- Two capabilities, `perception_range_eo_m` and `perception_range_ir_m`. Rejected:
  it doubles the wiring and splits the single "how far can I perceive" question the
  controller actually asks; the per-band detail stays available in `eoir_status`.
- A fused scalar that blends both bands. Rejected: the bands degrade under
  different physics, so a blend would hide the band-selection decision; the
  maximum preserves it.
- Naming the globally most-degraded factor in the recommendation. Rejected as
  misleading: the dead band's factor can be the global minimum while the best band
  is limited by something else, so the limiter is computed for the best band.

## Revisit triggers

- A controller needs per-band perception capabilities (then split, or add the
  bands to `extra`).
- The terrain line-of-sight `detection_confidence` (ADR 0078) should feed a
  target-detectability capability distinct from the clear-field range.
- The status floors prove mis-scaled for a very different platform envelope (then
  read them from the profile, the shared ADR 0038 revisit trigger).
