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
- BL-004 [planned] (L1) State machine wired to derived OperatorState and CommsState.
- BL-005 [in-progress] (L1) Thermal subsystem with two-state model. Two-state lumped model (junction + enclosure) wired through the engine so the FSM thermal-headroom guard reads live junction temperature and the battery's cell temperature tracks the enclosure. `thermal_status` MCP tool added; thermal Kalman filter active with shrinking covariance.
- BL-005a [in-progress] (L1) APU subsystem (solar PV + MPPT, methanol fuel cell, vehicle tether, USB-C PD-in). Subsystem, per-source Kalman, and `apu_status` tool wired; see ADR-0015.
- BL-005b [planned] (L1) PMU/PDU subsystem (bus regulation, source arbitration, CC/CV charge profile, dual-slot battery hot-swap). Lifts `charge_limit_w` and the offered/accepted clamp off `PowerSubsystem` onto a new `PmuSubsystem`. Supersedes ADR-0015. New ADR documents the dual-slot hot-swap state machine (primary + secondary battery, PMU arbitrates the active source; the inactive slot can be removed without bus collapse).
- BL-006 [planned] (L1) Hardware profile schema model + validator.
- BL-007 [in-progress] (L1) Compute subsystem with load curves from the profile. Load fraction set via `compute.set_load_pct` or `set_inference_rate`; draw watts come from the profile's piecewise-linear `load_curve`. The engine reads `compute.draw_w` each tick and feeds it into both power (electrical draw) and thermal (junction dissipation). Thermal throttling automatically caps delivered load. `compute_status` MCP tool added.
- BL-008 [planned] (L1) Storage subsystem with wear curve.
- BL-009 [planned] (L1) Environmental sensor pack subsystem.
- BL-010 [planned] (L1) Position subsystem (GNSS + 9-DoF IMU).
- BL-011 [planned] (L1) Biometrics subsystem (parametric, not physiology-grounded).
- BL-012 [planned] (L1) Comms subsystem with link envelopes.
- BL-013 [planned] (L1) Inference subsystem (local + cloud paths).
- BL-014 [planned] (L1) Scenario YAML loader + injectors.
- BL-015 [planned] (L1) SQLite schema + Alembic baseline migration.
- BL-016 [planned] (L1) Audit JSONL hash chain (optional).
- BL-017 [planned] (L1) `state_history` query path against SQLite.
- BL-018 [planned] (L1) Self-model assess + explain + viability wired to estimators.

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
