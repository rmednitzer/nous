# STATUS

Project phase and per-document maturity. Authoritative for "is this real
yet?" questions.

## Deployment posture

The single-VM reference instance (`nous-prod-01`) tracks `main` automatically. A systemd timer (`nous-auto-update.timer`) polls `origin/main` every 5 minutes and, if the remote HEAD has advanced, fast-forwards the working tree, re-runs `deploy/install.sh`, and restarts `nous.service`. Every merged PR therefore reaches the live VM within ~5 minutes with no manual intervention. See `docs/deployment.md` for the operational details and the abort-the-loop procedure. The host FQDN is intentionally not advertised in the repo (ADR 0017); the public face is the showcase under `docs/showcase/`. Two deployment failure modes found on `nous-prod-01` are closed in code: `deploy/install.sh` no longer installs `auto-update.sh` onto itself (the self-install errored under `set -e` and aborted every deploy after the `git reset`, the root cause of the freeze; BL-063), and `deploy/auto-update.sh` now rolls `HEAD` back and reinstalls the previous good artifacts on any failed deploy. The VM was manually resynced on 2026-05-28 (restarted onto current `main`; verified 29 tools, calibrated self-model, `audit.degraded:false`, so AUDIT N2 is cleared). A separate fix (BL-064 / ADR 0024) makes the engine tick at process scope: under `stateless_http=True` the per-request server lifespan had been rebooting the engine on every tool call, so `tick` and the FSM never advanced.

Last reviewed: 2026-06-01 ([`docs/audit-2026-06-01.md`](docs/audit-2026-06-01.md),
cadence delta; the BL-016 audit hash chain landed behind ADR 0025).
Prior pass 2026-05-27 second pass (delta audit at HEAD
``563175a``, post the ``claude/audit-carryforwards-2026-05-27``
stack: six 2026-05-27 carry-forwards closed (H2 mypy strict for
tests, N3 ``state_get`` enrichment, N4 snapshot parity test, N7
MISB decoder symmetry, N16 hypothesis-db hygiene doc, N17 bandit
suppressions catalog), plus first implementation increments for
the N8 ADR programme (ADR 0019 seed plus clock seams, ADR 0020
subsystem-physics invariants). ADR 0021 (per-subsystem tool
modules) and ADR 0022 (runtime safety enforcer) remain
unimplemented; each is its own multi-PR programme. Live-VM
action (N2) unchanged. See
[`docs/audit-2026-05-27b.md`](docs/audit-2026-05-27b.md) for
the delta and [`docs/audit-2026-05-27.md`](docs/audit-2026-05-27.md)
for the prior baseline.

Deployment-side status note: the L1 subsystem rollout has been on
`origin/main` since PR #38, so the auto-update timer lands the
current thirty-tool surface on the live VM on the next poll after
`origin/main` advances (no-op when the remote HEAD is unchanged).
Eight audit findings have closed since the 2026-05-23 baseline and
the post-baseline §10 re-audit: **C3** (FastMCP lifespan ticks the
engine, PR #40 + #42 follow-up), **C6** (CI policy greps enforce
em-dash and private-repo bans, PR #41), **N1** (deployment drift
between development line and `main`, PR #38), plus the
regression-pin closure of **C1**, **C4**, **C5**, **H3**, and
**M8** under PR #44 (`tests/regression/test_audit_findings.py`).
**N2** (live audit sink degraded) carries forward as the next
live-VM action item. See
[`docs/audit-2026-05-24.md`](docs/audit-2026-05-24.md) for the
fresh code-index audit and the validation against the conformance
documents; the cadence and the regression-pin pattern are codified
in [ADR 0023](docs/adr/0023-audit-cadence-and-regression-suite.md).
365 pytest tests pass at HEAD `fb8356f` (up from 351 at the §10
re-audit).

## Maturity taxonomy

- **stable** -- public contract, breaking changes go through deprecation;
  ADR governs changes.
- **in-progress** -- the file or component exists and is wired up, but the
  contract is still moving; expect churn.
- **planned** -- referenced from the backlog (`docs/backlog.md`), not yet
  scaffolded.

## Phase table

| Phase | Name | State | Scope |
|-------|------|-------|-------|
| L0 | Scaffold | stable | Layout, governance docs, audited tool surface, FSM, engine tick, hardware-profile loader, OAuth issuer. v0.1 shipped; the FastMCP lifespan now drives `tick_loop` so the live server advances state (PR #40 + #42). |
| L1 | Subsystem models + state machine | in-progress | All ten subsystems (power, APU, thermal, compute, inference, storage, comms, position, sensors, biometrics) implement step / truth / sensor_obs with live estimators; the state machine transitions on derived OperatorState and CommsState. Self-model layer (BL-018) now emits real capability claims; scenario loader / injectors / runner (BL-014) drive the engine end-to-end; SQLite migration (BL-015) and FSM transition persistence (BL-017) ship. The audit hash chain (BL-016) ships behind ADR 0025 and the daily anchor (BL-031) behind ADR 0026; the SQLite audit mirror (BL-065) remains an optional follow-up. |
| L2 | claude.ai integration + scenarios | planned | HTTP transport with OAuth + Caddy lockdown in place; scenario pack runs end-to-end; biometrics physiology-grounded; profile hot-reload. |
| L3 | STPA completion + benchmarks | planned | STPA derived requirements complete; comms propagation model; learned self-model; multi-tenant claude.ai; real local inference; additional interop adapters. |

## Per-document maturity

| Document | State |
|----------|-------|
| `README.md` | in-progress |
| `AGENTS.md` | in-progress |
| `CLAUDE.md` | in-progress |
| `LIMITATIONS.md` | in-progress |
| `STATUS.md` | in-progress |
| `CONTRIBUTING.md` | in-progress |
| `SECURITY.md` | in-progress |
| `CHANGELOG.md` | in-progress |
| `docs/architecture.md` | in-progress |
| `docs/state-machine.md` | in-progress |
| `docs/tool-reference.md` | in-progress |
| `docs/hardware-profiles.md` | in-progress |
| `docs/deployment.md` | in-progress |
| `docs/releasing.md` | in-progress |
| `docs/backlog.md` | in-progress |
| `docs/adr/0001` through `docs/adr/0025` | stable (decisions, not implementations) |
| `docs/stpa/01..09` | in-progress |
| `docs/conformance/*` | in-progress |
| `docs/model-cards/*` | in-progress |

## Component maturity

| Component | State | Notes |
|-----------|-------|-------|
| `src/nous/server.py` (FastMCP wiring + tool surface) | in-progress | Thirty tools registered across device telemetry (T0), the ten subsystem reads (T0), self-model and estimators (T0), interop schema + codec (T0/T1), local inference + cap (T0/T1), scenarios and configuration (T2), and operational recovery (T2 `audit_resync`, T0 `audit_verify` for the BL-016 hash chain, T0 `audit_anchor_verify` for the BL-031 daily anchor). See `docs/tool-reference.md` for the full table. The tick loop runs at process scope (ADR 0024), not on the server lifespan. |
| `src/nous/tick.py` | in-progress | Async tick loop; the overrun branch checkpoints so cancellation lands even when every tick exceeds its budget (PR #42). |
| `src/nous/policy.py` | stable | Tier classification + admission. Changes require an ADR. |
| `src/nous/audit.py` | stable | JSONL append-only with a tamper-evident per-record hash chain (ADR 0025 / BL-016; `verify_chain` plus the `audit_verify` tool). Changes require an ADR. |
| `src/nous/audit_anchor.py` | in-progress | Daily anchor over the chain head (ADR 0026 / BL-031): `AnchorLog` appends one hash-linked anchor per UTC day, and `verify_anchors` (the `audit_anchor_verify` tool) cross-checks anchored heads against the chain across logrotate segments to catch tail truncation within the retention window. |
| `src/nous/runner.py` | stable | Audited execution wrapper. Changes require an ADR. |
| `src/nous/state/machine.py` | stable | FSM transition table. Changes require an ADR. |
| `src/nous/safety/enforcer.py` | in-progress | Runtime safety-enforcer foundation (ADR 0022): `SafetyEnforcer.check` returns a structured `SafetyResult` (approved / clamped / evidence) and counts per-constraint and total violations; `floor_threshold` and `ceiling_clamp` cover the SC-2 refusal and throttle-clamp shapes. Generic seam, no constraints pre-registered; the audit mirror (`Tier.SAFETY`) and the first FSM caller land in the wiring PR. |
| `src/nous/anthropic_client.py` | stable | Daily cap + prompt cache discipline. |
| `src/nous/engine.py` | in-progress | Tick orchestration; all ten L1 subsystems (power, APU, thermal, compute, inference, storage, comms, position, sensors, biometrics) wired through the tick loop. The sensors subsystem is the authoritative ambient source for thermal; the comms aggregator drives `state.comms_state` each tick. |
| `src/nous/subsystems/power.py` | in-progress | Li-ion + Peukert + thermal derate (BL-003). |
| `src/nous/subsystems/apu.py` | in-progress | Solar PV (MPPT) + methanol fuel cell + vehicle tether + USB-C PD-in (BL-005a). |
| `src/nous/subsystems/thermal.py` | in-progress | Two-state lumped model: junction + enclosure (BL-005). Drives the FSM thermal-headroom guard and the battery cell temperature. |
| `src/nous/subsystems/compute.py` | in-progress | Load fraction + profile-driven draw curve (BL-007). Authoritative load source for power and thermal. Auto-clips delivered load when thermal reports throttling. |
| `src/nous/subsystems/inference.py` | in-progress | Local-path inference (BL-013): profile-derived latency and energy per request; running totals; `set_continuous_rate` writes through to compute. Cloud path deferred. |
| `src/nous/subsystems/storage.py` | in-progress | NAND wear and capacity accounting (BL-008): one-shot `write(gib)` and sustained `set_write_rate`; wear inflated by `write_amplification` against a TBW endurance budget. |
| `src/nous/subsystems/comms.py` | in-progress | Per-link envelopes (BL-012): live RSSI / loss / throughput / age per radio; `tx` resets age; `set_link_state` for scenario overrides; aggregator drives FSM `state.comms_state`. |
| `src/nous/subsystems/position.py` | in-progress | Lat / lon / alt ground truth (BL-010) with dead-reckoning, GNSS fix gating, IMU drift bias. Profile sigmas advertised on the GNSS observation. |
| `src/nous/subsystems/sensors.py` | in-progress | Ambient temperature, humidity, baro pressure (BL-009). Authoritative ambient source for the thermal subsystem each tick. |
| `src/nous/subsystems/biometrics.py` | in-progress | Parametric biometrics ground truth (BL-011): HR / core temp / hydration / cognitive load with physiological clamps; profile sigmas advertised on the observation. L2 physiology model still out of scope. |
| `src/nous/estimators/power.py` | in-progress | 1-D Kalman over (SoC, voltage); covariance bound documented in the model card. |
| `src/nous/estimators/apu.py` | in-progress | Per-source 1-D Kalman; tracks four source channels plus the total. |
| `src/nous/estimators/thermal.py` | in-progress | 1-D Kalman per channel over (junction_c, enclosure_c); covariance shrinks under observation. Full multi-state filter lands with BL-028. |
| `src/nous/estimators/compute.py` | in-progress | 1-D Kalman per channel over (load_pct, draw_w); covariance shrinks under observation. Full multi-state EKF is BL-031a. |
| `src/nous/estimators/storage.py` | in-progress | 1-D Kalman per channel over (used_gib, wear_pct); slow process variance matches the physical reality of NAND wear. |
| `src/nous/estimators/comms.py` | in-progress | Per-link SIR particle filter (BL-030): N binary-state particles per link, sticky Markov transition conditioned on RSSI + loss, log-throughput observation model, systematic resampling. Deterministic under the engine seed. |
| `src/nous/estimators/position.py` | in-progress | Constant-velocity EKF over `(lat, lon, alt, v_*)` (BL-026). Velocity tracked as predict-only; full IMU observation channel lands with the situational-awareness fusion track (BL-061). |
| `src/nous/estimators/sensors.py` | in-progress | Multi-channel Kalman over (temp_c, humidity_pct, baro_kpa); validates against physical bounds, rejects without poisoning the central estimate. |
| `src/nous/estimators/biometrics.py` | in-progress | Multi-channel Kalman over biometric channels with physiological-bounds validation; `hydration_pct` added as a fourth tracked channel in BL-011. |
| `src/nous/self_model/*` | in-progress | `assess` / `explain` / `viability` (BL-018) read live estimator state and emit capability claims. BL-035 lands the Monte Carlo-based calibrated quantile mapping (default `mode="monte_carlo"`; legacy `"gaussian"` opt-out retained). |
| `src/nous/interop/*` | in-progress | Real adapter implementations for CoT, SensorThings, MISB KLV, NMEA 0183, STANAG 4774/4778, MQTT. `nous.interop.REGISTRY` exposes them; `interop_encode` / `interop_decode` MCP tools (T1) round-trip via the audited runner (BL-041). |
| `src/nous/anthropic_status.py` | in-progress | Surfaces the daily cap state for `anthropic_cap_status` (BL-021); `cap_exhausted_payload(exc, settings=...)` renders `CapExhausted` as the same JSON shape. |
| `src/nous/auth/oauth.py` | in-progress | File-backed issuer shape. |
| `src/nous/scenarios/*` | in-progress | `loader` parses YAML from disk into typed `Scenario` objects; `injectors` mutate the live engine for ten action kinds (FSM, biometrics, thermal, APU, comms, sensors, position, velocity, compute, inference); `runner` drives the engine through a scenario timeline and returns a JSON-safe report (BL-014). |
| `profiles/jetson-agx-orin.yaml` | in-progress | Reference profile with placeholder curves. |
| `deploy/*` | in-progress | Systemd / Caddy / logrotate / install.sh / cloud-init. |
| Test suite | in-progress | Unit, integration scaffold, stdio smoke. |

## Quality gates

- `make check` (ruff + mypy strict + pytest) is green on `main` and every
  feature branch before merge. 642 tests pass at HEAD (the ADR 0022
  safety-enforcer foundation plus its fail-closed hardening add the most
  recent 36; 580 at the
  2026-06-01 cadence audit, [`docs/audit-2026-06-01.md`](docs/audit-2026-06-01.md),
  where BL-031 / ADR 0026 added the daily-anchor suite).
- `make docs-build` (`mkdocs build --strict`) is warning-free.
- `make policy` (em-dash + private-repo greps via
  `scripts/policy_checks.sh`) is enforced in CI as the `policy` job
  (PR #41 closed AUDIT-2026-05-23 C6). The script forces
  `LC_ALL=C.UTF-8` so the `grep -P '\x{2014}'` rule compiles in any
  contributor locale, and treats grep exit `2` as a policy failure
  rather than a silent pass.
