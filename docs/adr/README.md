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
