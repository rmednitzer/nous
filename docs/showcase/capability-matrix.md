# Capability matrix

Per-subsystem, per-estimator view of what is real today and what is
not. The badges are defined in [Fidelity](fidelity.md). Each row
points at the backlog item that is expected to raise the badge.

Last reviewed: 2026-06-06.

> **Deployment note.** The badges below track `origin/main` (most
> recently the BL-013 cloud-path landing, PR #110). The live VM
> auto-updates from `main` within about five minutes of a merge (see
> [deployment](../deployment.md)), so it picks up a badge change on the next
> poll after `origin/main` advances. The earliest live MCP audit
> ([`docs/audit-2026-05-23.md`](../audit-2026-05-23.md)) predates the L1
> catch-up train; the 2026-06-06 audit
> ([`docs/audit-2026-06-06.md`](../audit-2026-06-06.md)) records the
> current state.

## Subsystems

| Subsystem | Implementation | Estimator | Model card | Backlog |
| --- | --- | --- | --- | --- |
| power | `filtered` (Li-ion + Peukert + thermal derate) | `filtered` (SoC + voltage Kalman) | [subsystem](../model-cards/subsystem-power.md), [estimator](../model-cards/estimator-power-soc.md) | BL-003 |
| apu | `filtered` (solar MPPT, methanol FC, vehicle, USB-C PD) | `filtered` (per-source Kalman) | [subsystem](../model-cards/subsystem-apu.md), [estimator](../model-cards/estimator-apu.md) | BL-005a |
| pmu / pdu | `planned` (lifts off PowerSubsystem) | `planned` | `planned` | BL-005b |
| thermal | `filtered` (two-state lumped: junction + enclosure, profile-driven) | `filtered` (per-channel Kalman with shrinking covariance) | [subsystem](../model-cards/subsystem-thermal.md), [estimator](../model-cards/estimator-thermal-kalman.md) | BL-005, BL-028 |
| compute | `filtered` (load fraction, profile-driven draw curve, thermal-throttle clip) | `filtered` (per-channel Kalman over load and draw) | [subsystem](../model-cards/subsystem-compute.md), [estimator](../model-cards/estimator-compute-kalman.md) | BL-007, BL-031a |
| storage | `filtered` (NAND wear, capacity accounting, write amplification) | `filtered` (per-channel Kalman over used and wear) | [subsystem](../model-cards/subsystem-storage.md), [estimator](../model-cards/estimator-storage-kalman.md) | BL-008 |
| sensors | `filtered` (temp / humidity / baro; authoritative ambient source) | `filtered` (multi-channel Kalman with bounds validation) | [subsystem](../model-cards/subsystem-sensors.md), [estimator](../model-cards/estimator-sensors-kalman.md) | BL-009 |
| position | `filtered` (lat / lon / alt dead-reckoning + GNSS fix gating + IMU drift) | `parametric` (v0.1 linear-Kalman passthrough with NaN/Inf validation; nonlinear IMU fusion is BL-061) | [estimator](../model-cards/estimator-position-kalman.md) | BL-010, BL-026 |
| biometrics | `filtered` (HR / core temp / hydration / cognitive load with physiological clamps) | `filtered` (multi-channel Kalman; physiology grounding is BL-040) | [estimator](../model-cards/estimator-biometrics-kalman.md) | BL-011, BL-029, BL-040 |
| comms | `filtered` (per-link envelopes drive FSM `state.comms_state` each tick) | `parametric` (per-link belief tracker; full transition particle filter is BL-030) | [estimator](../model-cards/estimator-comms-particle.md) | BL-012, BL-030, BL-048 |
| inference | `parametric` (local-path with profile-derived latency / energy / capacity; cloud path registered via `inference_cloud`, ADR 0034, routing the SC-5 fallback ladder to the capped Anthropic client and degrading to the local mock; call enrichment landed in BL-069 / ADR 0035: tier selection, adaptive thinking on the advanced tier, and streaming for long generations) | n/a | [local mock](../model-cards/inference-local-mock.md) | BL-013, BL-043, BL-069 |
| self model | `parametric` (assess / viability emit calibrated `p5`/`p50`/`p95` claims via Monte Carlo over the estimator posteriors; learned self-model is future) | n/a | [self-model](../model-cards/self-model.md) | BL-018, BL-035 |

## Cross-cutting surfaces

| Surface | Status | Notes |
| --- | --- | --- |
| audit (JSONL, output-hashed) | `filtered` | append-only with fsync + chmod 0600, plus the BL-016 per-record hash chain and the BL-031 daily anchor; redaction still flat (AUDIT-2026-05-23 C2). The live VM resynced 2026-05-28 (AUDIT-2026-05-23 N2 cleared; `audit.degraded:false` confirmed by the 2026-06-06 live probe). |
| policy + runner (tier-classified admission) | `filtered` | tiers consistent with ADR 0001 and 0013. Denial path still misses `exit_code=1` (AUDIT-2026-05-23 M1). |
| OAuth issuer | `filtered` for single-client lockdown; `planned` for L3 multi-tenant | BL-019, BL-059. File-store lock and refresh-family revocation still open (AUDIT-2026-05-23 H6, H7). |
| anthropic client (daily cap + prompt cache) | `filtered` | Flush-before-unlock race closed (AUDIT C1); test coverage in `tests/unit/test_anthropic_client.py`. BL-021 surfacing still planned. |
| interop adapters (CoT, MISB, NMEA, STANAG, SensorThings, MQTT) | `parametric` | Encoders emit standards-shaped output with timestamp freshness checks; conformance is self-declared and uncertified (`docs/conformance/`). |
| scenario injectors | `in-progress` | The scenario YAML loader and injectors are wired (BL-014): `apply_injection` drives the engine for ten injector kinds, surfaced by the `scenario_load` / `scenario_inject` MCP tools. |
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
