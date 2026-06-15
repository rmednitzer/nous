# Architecture Decision Records

| # | Title | Status | Date |
|---|-------|--------|------|
| 0000 | [Template](0000-template.md) | Template | 2026-05-20 |
| 0001 | [FastMCP server with a tiered policy + audited runner](0001-fastmcp-and-tiered-policy.md) | Accepted | 2026-05-20 |
| 0002 | [SQLite with Alembic, JSONL audit alongside](0002-sqlite-alembic-and-jsonl-audit.md) | Accepted | 2026-05-20 |
| 0003 | [Hardware-profile YAML as the source of truth](0003-hardware-profile-yaml.md) | Accepted | 2026-05-20 |
| 0004 | [Hand-rolled finite-state machine](0004-hand-rolled-fsm.md) | Accepted | 2026-05-20 |
| 0005 | [Anthropic client with a hard daily cap and prompt-cache discipline](0005-anthropic-client-and-daily-cap.md) | Accepted | 2026-05-20 |
| 0006 | [Internal vocabularies for OperatorState and CommsState](0006-internal-vocabularies.md) | Accepted | 2026-05-20 |
| 0007 | [Additive-surface rule beyond L0](0007-additive-surface-rule.md) | Accepted | 2026-05-20 |
| 0008 | [VM deployment pattern (Ubuntu 24.04 + systemd + Caddy)](0008-vm-deployment-pattern.md) | Superseded by ADR 0016 | 2026-05-20 |
| 0009 | [STPA-Pro as the safety analysis method](0009-stpa-pro-as-safety-method.md) | Accepted | 2026-05-20 |
| 0010 | [Self-model and estimation layer](0010-self-model-and-estimation-layer.md) | Accepted | 2026-05-20 |
| 0011 | [Interoperability adapters as a single Protocol](0011-interoperability-adapters.md) | Accepted | 2026-05-20 |
| 0012 | [Versioned schemas for profiles, scenarios, and tool I/O](0012-versioned-schemas.md) | Accepted | 2026-05-20 |
| 0013 | [Tier-classified subsystem read/write tools](0013-tier-classified-subsystems.md) | Accepted | 2026-05-20 |
| 0014 | [Docs site on MkDocs with GitHub Pages](0014-docs-site-mkdocs-pages.md) | Accepted | 2026-05-20 |
| 0015 | [APU is strictly auxiliary; the primary battery is the sole bus](0015-apu-strictly-auxiliary.md) | Accepted | 2026-05-20 |
| 0016 | [Deployment baseline upgrades to Ubuntu 26.04 LTS](0016-deployment-baseline-ubuntu-2604.md) | Accepted | 2026-05-20 |
| 0017 | [Public showcase site on the existing docs Pages target](0017-public-showcase-site.md) | Accepted | 2026-05-21 |
| 0018 | [FSM transition guards for STPA safety constraints](0018-fsm-guards-for-stpa-constraints.md) | Accepted | 2026-05-21 |
| 0019 | [Deterministic seed and clock seam at the engine boundary](0019-deterministic-seed-and-clock-seam.md) | Accepted | 2026-05-24 |
| 0020 | [Property-based invariants for subsystem physics](0020-subsystem-physics-invariants.md) | Accepted | 2026-05-24 |
| 0021 | [Per-subsystem MCP tool modules](0021-per-subsystem-tool-modules.md) | Accepted | 2026-05-24 |
| 0022 | [Runtime safety enforcer with structured result](0022-runtime-safety-enforcer.md) | Accepted | 2026-05-24 |
| 0023 | [Audit cadence and regression-suite pattern](0023-audit-cadence-and-regression-suite.md) | Accepted | 2026-05-24 |
| 0024 | [Engine lifecycle is process-scoped, not MCP-session-scoped](0024-engine-lifecycle-process-scope.md) | Accepted | 2026-05-28 |
| 0025 | [Tamper-evident audit hash chain](0025-tamper-evident-audit-hash-chain.md) | Accepted | 2026-06-01 |
| 0026 | [Daily audit anchor](0026-daily-audit-anchor.md) | Accepted | 2026-06-04 |
| 0027 | [Condition-driven auto-safing on tick](0027-condition-driven-auto-safing.md) | Accepted | 2026-06-05 |
| 0028 | [FSM failsafe reachability, classification, and label-driven safing](0028-fsm-reachability-and-label-driven-safing.md) | Accepted | 2026-06-05 |
| 0029 | [FSM remediation -- actuation, neutral recovery, and fail-closed robustness](0029-fsm-remediation-actuation-and-robustness.md) | Accepted | 2026-06-05 |
| 0030 | [FSM completeness -- uniform fault reachability from every powered mode](0030-fsm-fault-reachability-completeness.md) | Accepted | 2026-06-05 |
| 0031 | [Register the state_transition control tool](0031-state-transition-control-tool.md) | Accepted | 2026-06-06 |
| 0032 | [FSM terminal-control tools](0032-fsm-terminal-control-tools.md) | Accepted | 2026-06-06 |
| 0033 | [Complete the registered tool surface](0033-complete-tool-surface.md) | Accepted | 2026-06-06 |
| 0034 | [Register the cloud inference path](0034-cloud-inference-path.md) | Accepted | 2026-06-06 |
| 0035 | [Enrich the cloud inference call](0035-enrich-cloud-inference-call.md) | Accepted | 2026-06-06 |
| 0036 | [Tick-loop observability via OpenTelemetry](0036-tick-loop-observability-otel.md) | Accepted | 2026-06-06 |
| 0037 | [Schema migration workflow](0037-schema-migration-workflow.md) | Accepted | 2026-06-06 |
| 0038 | [Self-model situational awareness](0038-self-model-situational-awareness.md) | Accepted | 2026-06-06 |
| 0039 | [Engine start completes to the IDLE standby posture](0039-engine-start-completes-to-idle.md) | Accepted | 2026-06-06 |
| 0040 | [Stateful scenario sessions and deterministic tick stepping](0040-stateful-scenario-sessions.md) | Accepted | 2026-06-09 |
| 0041 | [Self-model publish target](0041-self-model-publish-target.md) | Accepted | 2026-06-09 |
| 0042 | [Confine scenario_load to a configured scenarios directory](0042-confine-scenario-load-to-a-directory.md) | Proposed | 2026-06-13 |
| 0043 | [Constant-time verification for OAuth bearer and refresh tokens](0043-constant-time-token-verification.md) | Proposed | 2026-06-13 |
| 0044 | [First-class failsafe action framework](0044-first-class-failsafe-action-framework.md) | Accepted | 2026-06-14 |
| 0045 | [Estimator innovation gating and health](0045-estimator-innovation-gating-and-health.md) | Accepted | 2026-06-14 |
| 0046 | [Declarative mode-requirements gate](0046-declarative-mode-requirements-gate.md) | Accepted | 2026-06-14 |
| 0047 | [Comms store-and-forward outbox with precedence triage](0047-comms-store-and-forward-outbox.md) | Accepted | 2026-06-14 |
| 0048 | [Stamp the audit exit_code on the runner's caught-exception path](0048-runner-exit-code-for-caught-errors.md) | Accepted | 2026-06-14 |
| 0049 | [Make the cap status read fail closed on a corrupt counter](0049-cap-status-fail-closed-on-corrupt-counter.md) | Accepted | 2026-06-14 |
| 0050 | [The audit chain head tracks the on-disk tail, not the fsync confirmation](0050-chain-head-tracks-on-disk-tail.md) | Accepted | 2026-06-14 |
| 0051 | [Comms link throughput is an achieved rate, not a packet size](0051-comms-throughput-is-an-achieved-rate.md) | Accepted | 2026-06-14 |
| 0052 | [Name the interop freshness gate's configuration faults distinctly from staleness](0052-interop-freshness-gate-failure-modes.md) | Accepted | 2026-06-14 |
| 0053 | [Propagation-aware comms link quality](0053-propagation-aware-comms-model.md) | Accepted | 2026-06-14 |
| 0054 | [Higher-fidelity comms propagation (path loss, diffraction, noise, antenna, fading)](0054-higher-fidelity-propagation.md) | Accepted | 2026-06-14 |
| 0055 | [Redact the runner's caught-exception body to the exception class](0055-runner-redacts-caught-exception-body.md) | Accepted | 2026-06-14 |
| 0056 | [Distinguish a cap-persistence failure from exhaustion, and reuse the client](0056-cap-persist-error-and-client-reuse.md) | Accepted | 2026-06-15 |
| 0057 | [Authorize the breaking rename of tick_advance's count fields](0057-tick-advance-field-rename.md) | Accepted | 2026-06-15 |
| 0058 | [Read estimator rejections through health, and stringify decode keys](0058-rejections-through-health-and-decode-key-coercion.md) | Accepted | 2026-06-15 |
| 0059 | [comms_state CONNECTED requires every configured link healthy](0059-comms-connected-requires-all-configured-links.md) | Accepted | 2026-06-15 |
| 0060 | [inference_local stays T1 (reversible) despite its usage counters](0060-inference-local-stays-reversible.md) | Accepted | 2026-06-15 |
| 0061 | [BPv7 bundle identity and a delivered-bundle ledger for the DTN layer](0061-dtn-bundle-identity-and-dedup.md) | Accepted | 2026-06-15 |
| 0062 | [Multi-node DTN mesh with custody transfer](0062-dtn-multi-node-mesh-with-custody.md) | Accepted | 2026-06-15 |
| 0063 | [Contact-graph routing and an explicit custody acknowledgement](0063-dtn-contact-graph-routing-and-custody-ack.md) | Accepted | 2026-06-15 |
| 0064 | [Persisting the DTN store across a restart](0064-dtn-store-persistence.md) | Accepted | 2026-06-15 |
| 0065 | [EMCON emission-control postures](0065-emcon-emission-control.md) | Accepted | 2026-06-15 |
| 0066 | [EMCON scheduled emission windows](0066-emcon-scheduled-emission-windows.md) | Accepted | 2026-06-15 |
| 0067 | [EMCON metadata minimisation](0067-emcon-metadata-minimisation.md) | Accepted | 2026-06-15 |
