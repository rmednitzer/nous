# Capability matrix

Per-subsystem, per-estimator view of what is real today and what is
not. The badges are defined in [Fidelity](fidelity.md). Each row
points at the backlog item that is expected to raise the badge.

Last reviewed: 2026-05-21.

## Subsystems

| Subsystem | Implementation | Estimator | Model card | Backlog |
| --- | --- | --- | --- | --- |
| power | `filtered` (Li-ion + Peukert + thermal derate) | `filtered` (SoC + voltage Kalman) | [subsystem](../model-cards/subsystem-power.md), [estimator](../model-cards/estimator-power-soc.md) | BL-003 |
| apu | `filtered` (solar MPPT, methanol FC, vehicle, USB-C PD) | `filtered` (per-source Kalman) | [subsystem](../model-cards/subsystem-apu.md), [estimator](../model-cards/estimator-apu.md) | BL-005a |
| pmu / pdu | `planned` (lifts off PowerSubsystem) | `planned` | `planned` | BL-005b |
| thermal | `stub` (returns ambient default) | `stub` (passthrough) | [estimator](../model-cards/estimator-thermal-kalman.md) | BL-005, BL-028 |
| compute | `stub` (idle draw only) | `stub` (passthrough) | `planned` | BL-007, BL-031a |
| storage | `stub` (fixed capacity) | `planned` | `planned` | BL-008 |
| sensors | `stub` (hardcoded reads) | `planned` | `planned` | BL-009 |
| position | `stub` (hardcoded covariance) | `stub` (labelled EKF, no Jacobian) | [estimator](../model-cards/estimator-position-ekf.md) | BL-010, BL-026 |
| biometrics | `stub` (threshold) | `stub` (passthrough) | [estimator](../model-cards/estimator-biometrics-kalman.md) | BL-011, BL-029, BL-040 |
| comms | `stub` (nominal `CONNECTED`) | `stub` (named particle filter, no resampling) | [estimator](../model-cards/estimator-comms-particle.md) | BL-012, BL-030, BL-048 |
| inference | `planned` (local + cloud paths) | n/a | [local mock](../model-cards/inference-local-mock.md) | BL-013, BL-043 |
| self model | `planned` (assess returns zeros) | n/a | `planned` | BL-018, BL-035 |

## Cross-cutting surfaces

| Surface | Status | Notes |
| --- | --- | --- |
| audit (JSONL, output-hashed) | `filtered` | append-only; redaction is shallow today (AUDIT C2). |
| policy + runner (tier-classified admission) | `filtered` | tiers consistent with ADR 0001 and 0013. |
| OAuth issuer | `filtered` for single-client lockdown; `planned` for L3 multi-tenant | BL-019, BL-059. |
| anthropic client (daily cap + prompt cache) | `filtered` with one known race | AUDIT C1; BL-021. |
| interop adapters (CoT, MISB, NMEA, STANAG, SensorThings, MQTT) | `stub` | All adapters explicitly claim "no conformance"; BL-024..BL-036. |
| scenario injectors | `planned` | The scenario YAML loads, but the v0.1 injectors do not yet mutate engine state. BL-014. |
| deterministic replay | `planned` | A `SimClock` with seed control would unlock replay; not yet scoped. |

## How to read this page

A row at `filtered` for both implementation and estimator means a
controller can use the matching MCP tool with the covariance that the
estimator advertises. A row at `stub` for either column means the
output is not yet calibrated; the showcase suppresses covariance for
those rows. Rows at `planned` are surfaces the architecture promises
but the code does not yet provide.

The matrix is reviewed alongside `docs/backlog.md`. When a backlog
item moves to `[done]`, the corresponding row is updated and, where
appropriate, the scenario gallery is regenerated to reflect the new
substance level.
