# STATUS

Project phase and per-document maturity. Authoritative for "is this real
yet?" questions.

## Deployment posture

The single-VM reference instance (`nous-prod-01`) tracks `main` automatically. A systemd timer (`nous-auto-update.timer`) polls `origin/main` every 5 minutes and, if the remote HEAD has advanced, fast-forwards the working tree, re-runs `deploy/install.sh`, and restarts `nous.service`. Every merged PR therefore reaches the live VM within ~5 minutes with no manual intervention. See `docs/deployment.md` for the operational details and the abort-the-loop procedure. The host FQDN is intentionally not advertised in the repo (ADR 0017); the public face is the showcase under `docs/showcase/`.

Last reviewed: 2026-05-23 (re-audit at HEAD `43d0db2`, post PRs #40
/ #41 / #42).

Deployment-side status note: the L1 subsystem rollout is now on
`origin/main` (PR #38 catch-up train), so the auto-update timer
lands the nineteen-tool surface on the live VM on its next poll.
Three audit-baseline criticals closed since the 2026-05-23 baseline:
**C3** (FastMCP lifespan ticks the engine, PR #40 + #42 follow-up),
**C6** (CI policy greps now enforce em-dash and private-repo
bans, PR #41), and **N1** (deployment drift -- `main` caught up).
**N2** (live audit sink degraded) carries forward as the next
live-VM action item. See [`docs/audit-2026-05-23.md`](docs/audit-2026-05-23.md)
§10 for the post-catch-up re-audit and the revised remediation
order.

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
| L1 | Subsystem models + state machine | in-progress | All ten subsystems (power, APU, thermal, compute, inference, storage, comms, position, sensors, biometrics) implement step / truth / sensor_obs with live estimators; the state machine transitions on derived OperatorState and CommsState. Self-model wiring (BL-018) is the remaining gap. |
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
| `docs/adr/0001` through `docs/adr/0017` | stable (decisions, not implementations) |
| `docs/stpa/01..09` | in-progress |
| `docs/conformance/*` | in-progress |
| `docs/model-cards/*` | in-progress |

## Component maturity

| Component | State | Notes |
|-----------|-------|-------|
| `src/nous/server.py` (FastMCP wiring + representative tools) | in-progress | Nineteen tools registered: ten subsystem `*_status` reads (power, apu, thermal, compute, storage, comms, position, sensors, biometrics, inference) + `comms_state` (FSM aggregator) + `device_info` + `device_health` + `state_get` + `state_history` + `self_model_assess` + `self_estimator_status` + `interop_formats` + `inference_local`. The new `tick_lifespan` async context manager drives `tick_loop` for the lifetime of the server and calls `engine.stop()` in a `finally` (PR #40 + #42). |
| `src/nous/tick.py` | in-progress | Async tick loop; the overrun branch checkpoints so cancellation lands even when every tick exceeds its budget (PR #42). |
| `src/nous/policy.py` | stable | Tier classification + admission. Changes require an ADR. |
| `src/nous/audit.py` | stable | JSONL append-only. Changes require an ADR. |
| `src/nous/runner.py` | stable | Audited execution wrapper. Changes require an ADR. |
| `src/nous/state/machine.py` | stable | FSM transition table. Changes require an ADR. |
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
| `src/nous/estimators/comms.py` | in-progress | Per-link belief tracker (BL-012); aggregate Estimate over (connected_links, total_links). Full transition particle filter (BL-030) deferred. |
| `src/nous/estimators/position.py` | in-progress | v0.1 pass-through with NaN/Inf/range validation (BL-010 plumbing); full constant-velocity EKF lands with BL-026. |
| `src/nous/estimators/sensors.py` | in-progress | Multi-channel Kalman over (temp_c, humidity_pct, baro_kpa); validates against physical bounds, rejects without poisoning the central estimate. |
| `src/nous/estimators/biometrics.py` | in-progress | Multi-channel Kalman over biometric channels with physiological-bounds validation; `hydration_pct` added as a fourth tracked channel in BL-011. |
| `src/nous/self_model/*` | planned | Assess/explain/viability shipped as stubs. |
| `src/nous/interop/*` | planned | Each adapter ships as a typed stub in v0.1. |
| `src/nous/auth/oauth.py` | in-progress | File-backed issuer shape. |
| `src/nous/scenarios/*` | planned | Loader + injectors shipped as stubs. |
| `profiles/jetson-agx-orin.yaml` | in-progress | Reference profile with placeholder curves. |
| `deploy/*` | in-progress | Systemd / Caddy / logrotate / install.sh / cloud-init. |
| Test suite | in-progress | Unit, integration scaffold, stdio smoke. |

## Quality gates

- `make check` (ruff + mypy strict + pytest) is green on `main` and every
  feature branch before merge. 351 tests pass at `43d0db2`.
- `make docs-build` (`mkdocs build --strict`) is warning-free.
- `make policy` (em-dash + private-repo greps via
  `scripts/policy_checks.sh`) is enforced in CI as the `policy` job
  (PR #41 closed AUDIT-2026-05-23 C6). The script forces
  `LC_ALL=C.UTF-8` so the `grep -P '\x{2014}'` rule compiles in any
  contributor locale, and treats grep exit `2` as a policy failure
  rather than a silent pass.
