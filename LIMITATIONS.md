# LIMITATIONS

This document is authoritative on what `nous` is *not* yet, and what it does
not aim to be at all. Read it before opening an issue claiming a missing
capability.

Last reviewed: 2026-05-23.

## L1. Pre-1.0

**State.** All public APIs (MCP tool surface, profile YAML schema, scenario
YAML schema, database tables) may change without notice between minor
versions until 1.0.

**Implication.** Do not pin a downstream consumer against a `nous` API
without a vendored copy.

**Tracking.** Locked when [STATUS.md](STATUS.md) flips to phase L3 and the
1.0 release notes ship (`docs/releasing.md`).

## L2. Simulator only

**State.** `nous` simulates a backpack inference appliance. It does not
control a physical device, and the v0.1 codebase does not even build with
the hardware drivers required to do so.

**Implication.** Anything that looks like a real-time output (CoT message,
MQTT publish, MISB KLV frame) is a *simulated* output produced from
simulated subsystem state. Do not connect a simulator instance to a
production C2 or TAK server without an explicit posture review.

**Tracking.** Out of scope for the project. A future sibling repo would be
needed to drive real hardware.

## L3. Single operator

**State.** The simulator models exactly one operator wearing the unit. There
is no team model, no buddy-pair handoff, and no multi-unit coordination.

**Implication.** OperatorState (NOMINAL / ELEVATED / STRESSED / IMPAIRED /
INCAPACITATED) refers to the single carried-by operator. Squad-level
behaviours need an external model.

**Tracking.** [BL-049] team-coordination model is `[planned]` for L3.

## L4. Anthropic call cap

**State.** Every Anthropic call from `inference_cloud` is counted against a
daily cap stored in `$NOUS_HOME/.anthropic_daily_count`. The default cap is
100 calls per UTC day. Once exhausted, `inference_cloud` refuses until the
counter rolls over.

**Implication.** A scenario that depends on more than 100 cloud inferences
per day will stop producing cloud outputs. The local mock (`inference_local`)
remains available.

**Tracking.** See ADR-0005. The cap is intentional; raise the env var
`NOUS_ANTHROPIC_DAILY_CAP` only with operator approval.

## L5. No hot-reload of profiles

**State.** Hardware profile YAML files are loaded once at engine
construction. A change to a profile requires restarting the process.

**Implication.** Scenarios cannot swap profiles mid-run. The CLI's
`scenario` subcommand reconstructs the engine for each invocation.

**Tracking.** [BL-039] hot-reload is `[planned]` for L2.

## L6. Parametric biometrics

**State.** Operator biometrics (heart rate, core temperature, hydration,
cognitive load proxy) are simulated by parametric models, not by a
biophysical model of human physiology. The estimators read those parametric
signals; the model card for `estimator-biometrics-kalman` documents the
bounds.

**Implication.** Do not use biometric outputs to make claims about real
operators. The point of the layer is to exercise the *self-model* code
path, not to replace medical-grade monitoring.

**Tracking.** Out of scope for v0.1. A physiology-grounded biometrics
model is `[planned]` for L2 in [BL-040].

## L7. First-order comms model

**State.** Radio links are modelled by first-order link budget, additive
white Gaussian noise on RSSI, and a particle filter for connection state.
There is no propagation model, no terrain blockage, and no mesh routing.

**Implication.** Comms scenarios are useful for exercising the *handling*
of degraded links (failover, queueing, mode transitions), not for
predicting actual RF performance.

**Tracking.** [BL-041] propagation-aware comms is `[planned]` for L3.

## L8. Li-ion only

**State.** The power subsystem models a Li-ion battery with a Peukert
correction and a thermal derate. Other chemistries (LiFePO4, solid state)
are not modelled in v0.1.

**Implication.** Power curves and SoC estimates assume Li-ion; the SoC
estimator's covariance bound (see the `estimator-power-soc` model card) is
calibrated for Li-ion only.

**Tracking.** [BL-042] alternative chemistries are `[planned]` for L2.

## L9. Mocked local inference

**State.** `inference_local` runs a mock that returns a fixed structured
response after a configurable latency. No actual model executes.

**Implication.** Latency, energy, and thermal contribution numbers reported
by the inference subsystem are *derived from the profile YAML*, not measured
from a running model. Do not benchmark against them.

**Tracking.** [BL-043] running a real local model (TensorRT-LLM or llama.cpp)
is `[planned]` for L3.

## L10. STPA scope v0.1

**State.** The STPA artefacts in `docs/stpa/` cover the simulator's top
losses, hazards, control structure, and a first pass at unsafe control
actions and loss scenarios. Coverage is *not* complete; derived requirements
are partial.

**Implication.** Do not cite the STPA as a finished safety case. It is a
work-in-progress safety analysis.

**Tracking.** [BL-044] STPA completion is `[planned]` for L3.

## L11. Single-tenant claude.ai integration

**State.** The OAuth issuer ships in single-client lockdown by default.
Multi-tenant deployment (multiple claude.ai workspaces against one `nous`
instance) is not supported.

**Implication.** Each claude.ai workspace needs its own `nous` deployment.

**Tracking.** Out of scope for v0.1. Multi-tenant is `[planned]` for L3 in
[BL-045].

## L12. No mesh, no DTN

**State.** Comms are point-to-point. There is no mesh networking, no
delay-tolerant networking (DTN), and no store-and-forward.

**Implication.** A scenario that needs DTN (e.g. C2 traffic surviving a
long radio blackout) has to live with the link being denied.

**Tracking.** Out of scope for v0.1.

## L13. Linear-Gaussian estimators only

**State.** All estimators are Kalman / EKF / UKF / particle filter. There
is no neural estimator, no learned residual model, and no online
parameter estimation.

**Implication.** Estimator covariance bounds are valid only inside the
Gaussian assumption. Heavy-tailed disturbances will inflate the actual
error beyond what the filter reports.

**Tracking.** Out of scope for v0.1.

## L14. Parametric self-model

**State.** The self-model layer aggregates estimator outputs into
capability claims (endurance, thermal headroom, inference capacity) by
parametric rule. There is no learned self-model.

**Implication.** Self-model claims are only as good as the parametric
rules. They are calibrated, not learned.

**Tracking.** [BL-046] learned self-model is `[planned]` for post-1.0.

## L15. v0.1 interop subset

**State.** The interop adapters in v0.1 cover CoT/TAK, OGC SensorThings,
MISB KLV, NMEA 0183, STANAG 4774/4778, and MQTT. They are sufficient for
a single-operator mission feed and a single sensor stream into a TAK
server.

**Implication.** A mission stack that requires Link 16, STANAG 4609 video,
or VMF will need additional adapters. The base adapter Protocol
(`src/nous/interop/base.py`) is the seam.

**Tracking.** [BL-047] additional adapters are `[planned]` for L3.

## L16. Documented but uncertified conformance

**State.** `docs/conformance/` documents the project's posture against each
standard it speaks. No standard is *certified*; conformance is a
self-declaration based on the spec.

**Implication.** Do not claim STANAG conformance on the basis of `nous`
alone.

**Tracking.** Out of scope.

## L17. Standalone, no internal dependencies

**State.** `nous` is a standalone codebase. It does not depend on any
other internal repository, public or private, and must remain so.

**Implication.** Code patterns may be ported by hand from other projects;
runtime dependencies on other internal projects are forbidden.

**Tracking.** Enforced by CI grep in the quality bar.
