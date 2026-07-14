# Capability matrix

Per-subsystem, per-estimator view of what is real today and what is
not. The badges are defined in [Fidelity](fidelity.md). Each row
points at the backlog item that is expected to raise the badge.

Last reviewed: 2026-06-21.

> **Deployment note.** The badges below track `origin/main` (most
> recently the BL-005b PMU power-management and BL-055 EO/IR perception
> subsystems). A host running the
> reference deployment auto-updates from `main` within about five minutes of a merge (see
> [deployment](../deployment.md)), so it picks up a badge change on the next
> poll after `origin/main` advances. The earliest live MCP audit
> ([`docs/audit-2026-05-23.md`](../audit-2026-05-23.md)) predates the L1
> catch-up train; the 2026-06-15b audit
> ([`docs/audit-2026-06-15b.md`](../audit-2026-06-15b.md)) records the
> current documentation and profile state.

## Subsystems

| Subsystem | Implementation | Estimator | Model card | Backlog |
| --- | --- | --- | --- | --- |
| power | `filtered` (Li-ion + Peukert + thermal derate) | `filtered` (SoC + voltage Kalman) | [subsystem](../model-cards/subsystem-power.md), [estimator](../model-cards/estimator-power-soc.md) | BL-003 |
| apu | `filtered` (solar MPPT, methanol FC, vehicle, USB-C PD) | `filtered` (per-source Kalman) | [subsystem](../model-cards/subsystem-apu.md), [estimator](../model-cards/estimator-apu.md) | BL-005a |
| pmu / pdu | `parametric` (bus regulation lifted off power: charge-limit clamp, CC/CV taper past the knee, dual-slot hot-swap arbitration; ADR 0075) | n/a (the power Kalman follows the active pack across the bus) | `planned` | BL-005b |
| thermal | `filtered` (two-state lumped: junction + enclosure, profile-driven) | `filtered` (per-channel Kalman with shrinking covariance) | [subsystem](../model-cards/subsystem-thermal.md), [estimator](../model-cards/estimator-thermal-kalman.md) | BL-005, BL-028 |
| compute | `filtered` (load fraction, profile-driven draw curve, thermal-throttle clip) | `filtered` (per-channel Kalman over load and draw) | [subsystem](../model-cards/subsystem-compute.md), [estimator](../model-cards/estimator-compute-kalman.md) | BL-007, BL-031a |
| storage | `filtered` (NAND wear, capacity accounting, write amplification) | `filtered` (per-channel Kalman over used and wear) | [subsystem](../model-cards/subsystem-storage.md), [estimator](../model-cards/estimator-storage-kalman.md) | BL-008 |
| sensors | `filtered` (temp / humidity / baro; authoritative ambient source) | `filtered` (multi-channel Kalman with bounds validation) | [subsystem](../model-cards/subsystem-sensors.md), [estimator](../model-cards/estimator-sensors-kalman.md) | BL-009 |
| position | `filtered` (lat / lon / alt dead-reckoning + GNSS fix gating + IMU drift) | `parametric` (v0.1 linear-Kalman passthrough with NaN/Inf validation; nonlinear IMU fusion is BL-026) | [estimator](../model-cards/estimator-position-kalman.md) | BL-010, BL-026 |
| biometrics | `filtered` (HR / core temp / hydration / cognitive load with physiological clamps) | `filtered` (multi-channel Kalman; physiology grounding is BL-040) | [estimator](../model-cards/estimator-biometrics-kalman.md) | BL-011, BL-029, BL-040 |
| eoir | `filtered` (per-band EO/IR detection-range envelope: atmospheric, signal-contrast, and calibration-drift factors, with terrain line-of-sight masking; ADR 0077/0078) | `filtered` (two-channel gated scalar Kalman over the band ranges) | [subsystem](../model-cards/subsystem-eoir.md), [estimator](../model-cards/estimator-eoir-kalman.md) | BL-055 |
| comms | `filtered` (per-link envelopes drive FSM `state.comms_state` each tick; propagation link budget, store-and-forward outbox, DTN mesh, and EMCON posture layered on top) | `parametric` (per-link SIR particle filter with a soft connected-links belief, BL-030; non-Gaussian, so no Gaussian covariance bound) | [subsystem](../model-cards/subsystem-comms.md), [estimator](../model-cards/estimator-comms-particle.md) | BL-012, BL-030, BL-048, BL-056, BL-060, BL-077 |
| inference | `parametric` (local-path with profile-derived latency / energy / capacity; cloud path registered via `inference_cloud`, ADR 0034, routing the SC-5 fallback ladder to the capped Anthropic client and degrading to the local mock; call enrichment landed in BL-069 / ADR 0035: tier selection, adaptive thinking on the advanced tier, and streaming for long generations) | n/a | [local mock](../model-cards/inference-local-mock.md) | BL-013, BL-043, BL-069 |
| self model | `parametric` (assess / viability emit calibrated `p5`/`p50`/`p95` claims via Monte Carlo over the estimator posteriors; learned self-model is future) | n/a | [self-model](../model-cards/self-model.md) | BL-018, BL-035 |

## Cross-cutting surfaces

| Surface | Status | Notes |
| --- | --- | --- |
| audit (JSONL, output-hashed) | `filtered` | append-only with fsync + chmod 0600, plus the BL-016 per-record hash chain and the BL-031 daily anchor; redaction still flat (AUDIT-2026-05-23 C2). The live VM resynced 2026-05-28 (AUDIT-2026-05-23 N2 cleared; `audit.degraded:false` confirmed by the 2026-06-14b live probe). |
| policy + runner (tier-classified admission) | `filtered` | tiers consistent with ADR 0001 and 0013. Denial path still misses `exit_code=1` (AUDIT-2026-05-23 M1). |
| OAuth issuer | `filtered` for single-client lockdown; `planned` for L3 multi-tenant | BL-019, BL-059. File-store lock and refresh-family revocation still open (AUDIT-2026-05-23 H6, H7). |
| anthropic client (daily cap + prompt cache) | `filtered` | Flush-before-unlock race closed (AUDIT C1); test coverage in `tests/unit/test_anthropic_client.py`. BL-021 surfacing still planned. |
| interop adapters (CoT, MISB, NMEA, STANAG, SensorThings, MQTT) | `parametric` | Encoders emit standards-shaped output with timestamp freshness checks; conformance is self-declared and uncertified (`docs/conformance/`). |
| scenario injectors | `in-progress` | The scenario YAML loader and injectors are wired (BL-014): `apply_injection` drives the engine for ten injector kinds, surfaced by the `scenario_load` / `scenario_inject` MCP tools. |
| store-and-forward outbox | `filtered` | Bounded, precedence-ordered outbox holds packages when a link is degraded or denied and drains them as the link recovers (BL-077, ADR 0047); surfaced by `comms_outbox` / `comms_enqueue` / `comms_flush`. |
| DTN mesh | `parametric` | Multi-node BPv7-style mesh: `dtn_send` originates bundles routed by contact-graph routing with custody transfer, retransmit, dedup, and a SQLite-persisted store that survives a restart (BL-056, ADR 0061-0064). Nodes and contacts are abstract, not RF-modelled. |
| EMCON emission control | `filtered` | Operator emission posture at the `tx()` seam: named profiles, duty-cycle windows, and metadata minimisation, with denied or closed-window sends auto-triaged to the outbox (BL-060, ADR 0065-0067); surfaced by `emcon_status` / `emcon_set`. |
| deterministic seed + clock seam | `filtered` | An injected `now_s` clock seam and a seeded engine RNG (ADR 0019) make a run reproducible; full record-and-replay tooling is still planned. |

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
