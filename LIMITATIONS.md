# LIMITATIONS

This document is authoritative on what `nous` is *not* yet, and what it does
not aim to be at all. Read it before opening an issue claiming a missing
capability.

Last reviewed: 2026-06-14 ([`docs/audit-2026-06-14b.md`](docs/audit-2026-06-14b.md), full fresh adversarial and validation pass post BL-048 / BL-088). Prior: 2026-06-06 ([`docs/audit-2026-06-06.md`](docs/audit-2026-06-06.md), full-repo validation audit).

## L1. Pre-1.0

**State.** All public APIs (MCP tool surface, profile YAML schema, scenario
YAML schema, database tables) may change without notice between minor
versions until 1.0.

**Implication.** Do not pin a downstream consumer against a `nous` API
without a vendored copy.

**Tracking.** Locked when [STATUS.md](STATUS.md) flips to phase L3 and the
1.0 release notes ship (`docs/releasing.md`).

## L2. Model-only digital twin (no hardware in the loop)

**State.** `nous` is a simulation-based digital twin: it models an edge-AI
inference appliance in software but is not coupled to a physical unit. It
does not control real hardware, ingests no live device telemetry, and the
v0.1 codebase does not even build with the hardware drivers required to do
so. In the digital-twin taxonomy it is a digital *model* (no automated
physical / digital data exchange), not a digital *shadow* (a one-way live
feed) or a bidirectionally-synced twin.

**Implication.** Anything that looks like a real-time output (CoT message,
MQTT publish, MISB KLV frame) is a *modelled* output produced from simulated
subsystem state. Do not connect an instance to a production C2 or TAK server
without an explicit posture review.

**Tracking.** Out of scope for the project. A future sibling repo would be
needed to drive real hardware and close the loop into a hardware-synced twin.

## L3. Single operator

**State.** The simulator models exactly one operator wearing the unit. There
is no team model, no buddy-pair handoff, and no multi-unit coordination.

**Implication.** OperatorState (NOMINAL / ELEVATED / STRESSED / IMPAIRED /
INCAPACITATED) refers to the single carried-by operator. Squad-level
behaviours need an external model.

**Tracking.** [BL-049] team-coordination model is `[planned]` for L3.

## L4. Anthropic call cap

**State.** The Anthropic daily cap is implemented in `anthropic_client.py`
and counted against `$NOUS_HOME/.anthropic_daily_count`; the default cap is
100 calls per UTC day, and once exhausted the client fails closed with
`CapExhausted` until the counter rolls over. The cap state is exposed through
the `anthropic_cap_status` tool (T0). The `inference_cloud` tool (T2) that
consumes the cap is now registered (ADR-0034): it routes through the
`InferenceFallback` ladder, which degrades to the local mock when the cap is
exhausted, comms are down, or the cloud call fails, so a controller always
gets an answer.

**Implication.** A scenario that depends on more than 100 cloud inferences
per day stops producing cloud outputs and is served by the local mock
(`inference_local` directly, or `inference_cloud` degraded to the mock).

**Tracking.** See ADR-0005 (cap), ADR-0034 (cloud path registration), and
ADR-0035 (cloud-call enrichment). The cap is intentional; raise the env var
`NOUS_ANTHROPIC_DAILY_CAP` only with operator approval. Cloud-call enrichment
(adaptive thinking, capability-guarded; streaming for long generations;
model-tier selection surfaced as `inference_cloud(tier=...)`) landed under
BL-069.

## L5. Profile hot-reload is runtime-only, not mid-scenario

**State.** A running engine reloads its hardware profile through the
`profile_reload` tool, which re-reads the YAML, re-validates it through
the schema gate, and rebuilds every subsystem and estimator while
preserving FSM mode and tick counter (`Engine.reload_profile`, BL-039).
A failed load (missing file, bad schema) keeps the previous profile
mounted.

**Implication.** What is not supported is swapping profiles in the
middle of a scenario run. The CLI's `scenario` subcommand reconstructs
the engine for each invocation, and the scenario timeline has no
profile-swap injector.

**Tracking.** [BL-039] runtime hot-reload is `[in-progress]` (shipped);
mid-scenario profile swap stays out of scope for v0.1.

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

## L7. Comms propagation model

**State.** A link with a `propagation` block solves its RSSI, packet loss,
and SNR-derived capacity each tick from a link budget over the
device-to-peer geometry (BL-048, ADR 0053), with the BL-088 / ADR 0054
higher-fidelity terms layered on: a log-distance path-loss exponent for the
environment, a single knife-edge diffraction loss for a discrete
obstruction, a kTB thermal-noise floor, a directional antenna pattern keyed
on the bearing to the peer, and a Rician multipath fast-fade. A particle
filter still tracks connection state. A link that opts into terrain
(`use_terrain`) samples a procedural elevation field along the path and runs
multi-edge Bullington diffraction over it (BL-089, ADR 0072). What is not
modelled: a real surveyed DEM (the field is procedural, not a fetched dataset),
frequency-selective fading, and mesh or multi-hop routing. A link with no
propagation block stays at its static nominal.

**Implication.** Comms scenarios reproduce graded, geometry- and
environment-driven degradation (range, clutter, a ridge, antenna pointing,
and fading all move the link), not just scripted link states. The terrain
model is multi-edge over a procedural elevation field, so it captures the
controlling ridges along the path; it is not a surveyed DEM, so it
demonstrates the physics rather than a specific real location.

**Tracking.** Multi-edge terrain diffraction over a procedural world shipped
under [BL-089] (ADR 0072); a real surveyed-DEM loader and frequency-selective
fading remain out of scope for v0.1. Mesh routing is part of the [BL-056]
delay-tolerant-networking layer.

## L8. Li-ion only

**State.** The power subsystem models a Li-ion battery with a Peukert
correction and a thermal derate. Other chemistries (LiFePO4, solid state)
are not modelled in v0.1.

**Implication.** Power curves and SoC estimates assume Li-ion; the SoC
estimator's covariance bound (see the `estimator-power-soc` model card) is
calibrated for Li-ion only.

**Tracking.** [BL-042] alternative chemistries are `[planned]` for L3.

## L9. Mocked local inference

**State.** `inference_local` runs a mock: it returns a synthetic response
that echoes the prompt head, with latency, energy, and token-rate figures
derived from the profile's local-inference curve (latency is
`n_tokens / tok_per_s_p50`, not a fixed delay). No actual model executes.

**Implication.** Latency, energy, and thermal contribution numbers reported
by the inference subsystem are *derived from the profile YAML*, not measured
from a running model. Do not benchmark against them.

**Tracking.** [BL-043] running a real local model (TensorRT-LLM or llama.cpp)
is `[planned]` for L3.

## L10. STPA scope

**State.** The STPA artefacts in `docs/stpa/` cover the simulator's losses,
hazards, control structure, unsafe control actions, and loss scenarios, and the
derived requirements are now complete: every safety constraint carries at least
one enforced requirement, with the end-to-end traceability and the pinning
tests in `docs/stpa/11-coverage.md` (BL-044).

**Implication.** The STPA is internally complete for the simulator, but it
remains a teaching artefact, not a certified safety case for a real device
(`docs/stpa/01-purpose.md`); conformance is self-declared (L16). Do not cite it
as a finished safety case for hardware.

**Tracking.** [BL-044] STPA derived-requirements completion + coverage report
is `[done]`. A real-device safety case is out of scope for the simulator.

## L11. Single-tenant claude.ai integration

**State.** The OAuth issuer ships in single-client lockdown by default.
Multi-tenant deployment (multiple claude.ai workspaces against one `nous`
instance) is not supported.

**Implication.** Each claude.ai workspace needs its own `nous` deployment.

**Tracking.** Out of scope for v0.1. Multi-tenant is `[planned]` for L3 in
[BL-045].

## L12. DTN mesh is simulated over abstract nodes, not a real radio network

**State.** The full delay-tolerant-networking layer is now present (BL-056,
ADR 0061-0064): a multi-node mesh originates BPv7-style bundles with
`dtn_send`, routes them hop by hop with contact-graph routing over a
time-windowed contact schedule, transfers custody with retransmission and a
deduplicated custody acknowledgement, and checkpoints the whole store to
SQLite so a custodial bundle survives a restart. The single-hop
store-and-forward outbox (BL-077, ADR 0047) still backs the device's own
link. What remains simulated rather than real is the substrate: the mesh
peers are abstract hold-and-forward nodes, the contacts come from a
configured `dtn` profile section rather than neighbour discovery, and
inter-node loss is a Bernoulli draw rather than modelled RF propagation.

**Implication.** A bundle can reach the controller over a relayed multi-hop
path and survive both a link drop and a process restart, but the topology is
authored, not discovered, and the mesh links do not carry the per-link RF
physics (RSSI, range, fade) the device's own comms links do.

**Tracking.** DTN layer done under BL-056 (ADR 0061-0064); single-hop outbox
under BL-077. Neighbour discovery and RF-physics-backed mesh links are not
tracked for v0.1.

## L13. Linear-Gaussian estimators (the position EKF excepted)

**State.** The position estimator is a nonlinear error-state Extended Kalman
Filter that fuses GNSS with an IMU in a local east-north-up frame (BL-026,
ADR 0073, ADR 0076): the unicycle process couples the axes through `sin`/`cos`
of the heading, so `predict` propagates the covariance through the analytic
Jacobian, and the accelerometer and yaw-rate gyro biases are carried as two
error states that GNSS observes through the cross-covariance. The remaining
estimators are linear Kalman filters (scalar or multi-channel) or a particle
filter (comms link state). There is no neural estimator and no learned residual
model.

**Implication.** The linear estimators' covariance bounds are valid only inside
the Gaussian assumption; heavy-tailed disturbances inflate the actual error
beyond what the filter reports. The position EKF is nonlinear but still
Gaussian: its bound holds while the linearisation is good (it degrades far from
the anchor, or during long IMU-only coasts once a bias drifts faster than the
random-walk process noise tracks). The bias states are observable only under
motion and a fix, so they are meaningful only after the platform has manoeuvred.

**Tracking.** The position EKF + IMU fusion shipped under [BL-026] (ADR 0073);
error-state IMU-bias estimation followed under the same backlog item (ADR 0076).
Nonlinear filters for the other channels are out of scope for v0.1.

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
runtime dependencies on other internal projects are forbidden. The physics
inputs are injected behind narrow seams (the engine `rng`, the `position_fn`
getter, the `WorldSource` terrain, the `set_velocity` / `set_motion` motion
commands), so an out-of-tree adapter, including one backed by an external
physics engine, can drive the twin without `nous` importing it (ADR 0074). The
in-tree default for each seam stays standalone.

**Tracking.** The em-dash rule is enforced today by
`scripts/policy_checks.sh` (the `policy` CI job and `make policy`
locally; PR #41 closed AUDIT-2026-05-23 C6). The private-repo rule
ships as a structured extension point in the same script:
`private_repo_patterns` is currently empty, so the deny-list grep
does not actively scan and L17 is held by author discipline. Append
a specific private name to `private_repo_patterns` to activate the
grep against that name; CI will then fail any commit that introduces
a reference.

## L18. Audit tamper-evidence is bounded by the retention window

**State.** The audit JSONL is a per-record hash chain (ADR 0025 /
BL-016): each line commits to its predecessor, so any in-place edit or
mid-stream deletion, insertion, or reordering breaks the chain at a
point `verify_chain` (and the `audit_verify` tool) reports. The chain
alone does not detect tail truncation, since dropping the most recent
records leaves a shorter but internally consistent chain. The BL-031
daily anchor (ADR 0026, `audit_anchor_verify`) closes that gap: it pins
the chain head once per UTC day into a separate append-only file and
flags an anchored head that has gone missing from the chain. The
combined property is "no undetected truncation within the retention
window." Both surfaces are evidence, not access control.

**Implication.** A passing `audit_anchor_verify` means no records were
dropped from the end of the log since the most recent anchor that is
still within retention; it cannot speak to content that has aged out of
the on-disk segments. The chain and the anchor supplement the
append-only bit (`chattr +a`) and off-host shipping; they do not replace
them. The anchor verifier also assumes the bundled logrotate naming; a
deployment that rotates the audit log differently needs a matching
segment reader (ADR 0026 revisit trigger).

**Tracking.** [BL-031] is `[in-progress]` (shipped). Signed anchors for
regulated deployments are tracked under [BL-059].

## L19. EO/IR is a capability envelope, not imagery

**State.** The EO/IR subsystem (BL-055, ADR 0077) models the payload as a
per-band effective detection range, the product of a clear-air reference
range and atmospheric, signal, and calibration factors. It carries no
imagery, no per-object track, and no learned detector. The Johnson
detection / recognition / identification ranges are a deterministic
geometric scaling of the detection range, not a probability of
identification. Thermal contrast is computed against a single profile
target temperature, not a background distribution, and the atmospheric
model is a Koschmieder meteorological-range cap, not a spectral
transmittance calculation. Terrain line-of-sight masking (ADR 0078) covers
one configured target at a time with a straight-line clearance test (no
earth curvature or refraction); the reported `detection_confidence` is a
geometric range fraction, not a probability of detection.

**Implication.** The detection ranges report which band can reach how far
under the current ambient and calibration, the legible capability a
controller selects a band on. They are *derived from the profile and the
sensor-pack seam*, not measured from an optical chain; do not use them for
real targeting or detection-performance prediction.

**Tracking.** [BL-055] is `[done]`. The envelope (ADR 0077), terrain
line-of-sight masking (ADR 0078), and the self-model `perception_range_m`
capability (ADR 0079) have all shipped.
