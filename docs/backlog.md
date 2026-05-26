# Backlog

Line-item tracker. Each item carries a `BL-NNN` id, a one-line summary,
a status (`[planned]`, `[in-progress]`, `[done]`), and the milestone
(`L0` .. `L3`). Reference the id in commit messages and PR titles where
possible.

## L0 -- Scaffold

- BL-001 [in-progress] (L0) Project layout, governance docs, audited tool surface, FSM, engine tick, hardware-profile loader. *This PR.*

## L1 -- Subsystem models and state machine

- BL-002 [in-progress] (L1) FastMCP server: full subsystem read tool surface. Power and APU tools now return real engine values; remaining subsystems still stub.
- BL-003 [in-progress] (L1) Power subsystem (Li-ion + Peukert + thermal derate). Subsystem and SoC Kalman live; controller wiring in `server.py::power_status`.
- BL-004 [in-progress] (L1) State machine wired to derived OperatorState and CommsState. `state.operator_state` is now refreshed each tick from `derive_operator(biometrics_est.state())`; `state.comms_state` is refreshed from `comms.derive_state()`. Both labels (plus reasons) appear in the engine snapshot. The FSM itself does not yet auto-trigger on the labels; that gate lands with BL-022 / DR-2.
- BL-005 [in-progress] (L1) Thermal subsystem with two-state model. Two-state lumped model (junction + enclosure) wired through the engine so the FSM thermal-headroom guard reads live junction temperature and the battery's cell temperature tracks the enclosure. `thermal_status` MCP tool added; thermal Kalman filter active with shrinking covariance.
- BL-005a [in-progress] (L1) APU subsystem (solar PV + MPPT, methanol fuel cell, vehicle tether, USB-C PD-in). Subsystem, per-source Kalman, and `apu_status` tool wired; see ADR-0015.
- BL-005b [planned] (L1) PMU/PDU subsystem (bus regulation, source arbitration, CC/CV charge profile, dual-slot battery hot-swap). Lifts `charge_limit_w` and the offered/accepted clamp off `PowerSubsystem` onto a new `PmuSubsystem`. Supersedes ADR-0015. New ADR documents the dual-slot hot-swap state machine (primary + secondary battery, PMU arbitrates the active source; the inactive slot can be removed without bus collapse).
- BL-006 [in-progress] (L1) Hardware profile YAML loader now fails fast on missing files and malformed top-level structure; minimal schema gate enforces `name` presence. Full profile field model remains to be completed.
- BL-007 [in-progress] (L1) Compute subsystem with load curves from the profile. Load fraction set via `compute.set_load_pct` or `set_inference_rate`; draw watts come from the profile's piecewise-linear `load_curve`. The engine reads `compute.draw_w` each tick and feeds it into both power (electrical draw) and thermal (junction dissipation). Thermal throttling automatically caps delivered load. `compute_status` MCP tool added.
- BL-008 [in-progress] (L1) Storage subsystem with wear curve. NAND wear driven by physical writes (logical writes inflated by `storage.write_amplification`); endurance budget defaults to `capacity_gib * 600` GiB when `storage.tbw_gib` is unset. `write(gib)` and `set_write_rate(gib_per_s)` for one-shot and sustained workloads; paired 1-D Kalman estimator over (used_gib, wear_pct); `storage_status` MCP tool added.
- BL-009 [in-progress] (L1) Environmental sensor pack subsystem. Ambient temperature, humidity, and barometric pressure as ground truth; `set_temp_c`, `set_humidity_pct`, `set_baro_kpa` scenario seams. The engine reads `sensors.temp_c` each tick as the thermal subsystem's ambient input, replacing the `_default_ambient_c()` placeholder. New `EnvironmentalKalman` over the three channels with validation; `sensors_status` MCP tool added.
- BL-010 [in-progress] (L1) Position subsystem (GNSS + 9-DoF IMU). Ground-truth lat / lon / alt advanced by dead-reckoning each tick (`set_velocity(speed_mps, heading_deg)` + optional `vertical_mps`); profile sigmas from `sensors.position` are advertised on the GNSS observation. `set_fix(false)` simulates loss of fix (empty payload, EKF variance grows under `predict`); `set_imu_drift` lets a scenario express a biased IMU. `position_status` MCP tool added; the full EKF stays planned as BL-026.
- BL-011 [in-progress] (L1) Biometrics subsystem (parametric, not physiology-grounded). Heart rate, core temp, hydration, cognitive load as ground truth with physiological-range clamps; profile sigmas from `sensors.biometrics` advertised on the observation. `BiometricsKalman` extended with a `hydration_pct` channel. `biometrics_status` MCP tool added. L2 physiology model still out of scope.
- BL-012 [in-progress] (L1) Comms subsystem with link envelopes. Live per-link state from `profile["comms"]["links"]` (RSSI, loss, throughput, age); `tx(link_id, bytes)` resets age; links time out after `max_age_s`; `set_link_state` lets a scenario degrade or restore a link sticky. Engine derives `state.comms_state` from live links each tick via `derive()`. `comms_state` and `comms_status` MCP tools live; `CommsParticleFilter` upgraded from no-op stub to a per-link belief tracker (full transition particle filter is BL-030).
- BL-013 [in-progress] (L1) Inference subsystem (local + cloud paths). Local path lives in `subsystems/inference.py`: a request returns profile-derived latency (`tok_per_s_p50`) and energy (`energy_j_per_tok`); totals accumulate; `set_continuous_rate` writes through to `ComputeSubsystem.set_inference_rate` so a sustained workload propagates into draw watts. `inference_local` MCP tool now returns the cost figures; new `inference_status` MCP tool exposes the totals. Cloud path (fallback ladder + cap accounting) deferred to a follow-up ADR.
- BL-014 [in-progress] (L1) Scenario YAML loader + injectors. `load_scenario_file` reads YAML from disk; `apply_injection` drives the engine for ten injector kinds (FSM transitions, biometrics deltas, thermal ambient shifts, APU overrides, comms loss, sensor drift, position teleport, velocity, compute steer, inference request); `run_scenario` walks the timeline against a tick budget and returns a JSON-safe report. New `scenario_load` / `scenario_inject` MCP tools surface the runner to controllers.
- BL-015 [in-progress] (L1) SQLite schema + Alembic baseline migration. `alembic.ini` + `alembic/versions/0001_baseline.py` create `state_transitions` and `audit_entries` mirroring the SQLModel definitions in `db.py`. `alembic upgrade head` is wired through standard alembic configuration. Future schema evolution lands as additional revisions (BL-051).
- BL-016 [planned] (L1) Audit JSONL hash chain (optional).
- BL-017 [in-progress] (L1) `state_history` query path against SQLite. `StateTransitionLog` in `db.py` persists every successful FSM transition (and every guard refusal, with `denied:` prefix) to the `state_transitions` table; the `state_history` MCP tool prefers the SQLite rows when available and falls back to in-memory FSM history when the DB is unreachable.
- BL-018 [in-progress] (L1) Self-model assess + explain + viability wired to estimators. `assess(question, engine=...)` reads the live power / thermal / compute estimator state and emits calibrated `Capability` claims (endurance_min, thermal_headroom_c, inference_capacity_tok_per_s) with Gaussian quantile bands; `explain` renders them plus a limiting-driver line; `viability` checks structured or keyword-sniffed requirements against the `p5` band. New `self_model_viability` MCP tool. The engine's `state.last_capabilities` is refreshed each tick. Calibrated mapping replacement is BL-035.

## L2 -- claude.ai integration and scenarios

- BL-019 [stable] (L2) OAuth issuer wired into FastMCP via the SDK provider.
- BL-020 [planned] (L2) HTTP transport with OAuth and Caddy template.
- BL-021 [planned] (L2) Anthropic client cap surfacing + structured `CapExhausted` payload.
- BL-022 [planned] (L2) State machine refuses unsafe transitions per DR-2.
- BL-023 [planned] (L2) Scenario pack: env-monitoring, c2-degraded-comms, relay-mountain, operator-heat-strain, standalone-comms-hub, apu-solar-sustained, apu-fuelcell-overnight.
- BL-024 [planned] (L2) CoT/TAK adapter (XML encode + decode).
- BL-025 [planned] (L2) OGC SensorThings adapter.
- BL-026 [planned] (L2) Position EKF.
- BL-027 [planned] (L2) Power SoC estimator.
- BL-028 [planned] (L2) Thermal Kalman filter.
- BL-029 [planned] (L2) Biometrics Kalman filter.
- BL-030 [planned] (L2) Comms particle filter.
- BL-031 [planned] (L2) Daily audit hash chain (BL-016 follow-up).
- BL-031a [planned] (L2) Compute Kalman filter.
- BL-032 [planned] (L2) MISB KLV adapter.
- BL-033 [planned] (L2) NMEA 0183 adapter (pynmea2).
- BL-034 [planned] (L2) STANAG 4774/4778 confidentiality-label adapter.
- BL-035 [planned] (L2) Self-model assessment with calibrated quantiles per DR-1.
- BL-036 [planned] (L2) MQTT adapter (paho).
- BL-037 [planned] (L2) OTEL instrumentation on the tick loop.
- BL-038 [planned] (L2) Logrotate hardening (`postrotate chattr +a`).
- BL-039 [planned] (L2) Profile hot-reload.
- BL-040 [planned] (L2) Physiology-grounded biometrics model.
- BL-041 [planned] (L2) Tier-2/Tier-3 subsystem mutators (per ADR-0013).

## L3 -- STPA completion and benchmarks

- BL-042 [planned] (L3) Alternative battery chemistries (LiFePO4, solid state).
- BL-043 [planned] (L3) Real local inference (TensorRT-LLM or llama.cpp).
- BL-044 [planned] (L3) STPA derived requirements complete + coverage report.
- BL-045 [planned] (L3) Multi-tenant claude.ai integration.
- BL-046 [planned] (L3) Learned self-model (post-1.0).
- BL-047 [planned] (L3) Additional interop adapters (STANAG 4609 video, Link 16, VMF).
- BL-048 [planned] (L3) Propagation-aware comms model (terrain, fading).
- BL-049 [planned] (L3) Team coordination (multi-unit, buddy pair).
- BL-050 [planned] (L3) Model card coverage for every estimator.
- BL-051 [planned] (L3) Versioned schema migrations (`scripts/migrate_*.py`).
- BL-052 [planned] (L3) Tool reference autogenerated from FastMCP schemas.
- BL-053 [planned] (L3) Docs workflow + GitHub Pages deploy (depends on enabling Pages).
- BL-054 [planned] (L3) Self-driving demo wiring Anthropic + nous MCP via stdio.
- BL-055 [planned] (L3) Thermo-optical subsystem and estimator (EO/IR detection confidence, calibration drift, obscurant effects, and thermal contrast limits) with model card and profile-backed parameters.
- BL-056 [planned] (L3) External sensor mesh and DTN simulation layer (store-and-forward queues, TTL, custody and replay semantics) aligned to RFC 4838 architecture and BPv7 message behavior for degraded links.
- BL-057 [planned] (L3) SATCOM uplink/downlink channel model (startup latency, jitter, outage windows, energy coupling, and failover policy hooks) with scenario coverage for BLOS operation.
- BL-058 [planned] (L3) Local storage hardening and resilience model (wear, corruption windows, journaling recovery, retention windows, and at-rest protection posture).
- BL-059 [planned] (L3) OAuth/token-state hardening for regulated deployments (file permission checks, authenticated encryption at rest, rotation workflow, and tamper-evident audit events) aligned to OAuth 2.0 Security BCP guidance.
- BL-060 [planned] (L3) Cyber and OPSEC/EMCON policy layer (emission profiles, metadata minimization, silent/burst modes, and policy-driven comms denials) with explicit audit provenance.
- BL-061 [planned] (L3) Situational and tactical-awareness fusion outputs (confidence bands, staleness, source provenance, and degraded-mode recommendations) wired through self-model tools.
- BL-062 [in-progress] (L2) Public showcase site under the existing MkDocs Pages target: fidelity badges, FSM viewer, capability matrix, scenario telemetry generated by `scripts/gen_showcase_telemetry.py`. See ADR 0017.

## Tracking notes

- Items inherit the additive-surface rule (ADR-0007) once L0 ships.
- Items referenced from the STPA derived requirements (`docs/stpa/09-derived-requirements.md`) carry the DR-N cross-reference in their description when work begins.
