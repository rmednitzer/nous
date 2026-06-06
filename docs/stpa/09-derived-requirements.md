# 09 -- Derived requirements

Each row is a requirement that flows out of a safety constraint and into the
backlog. The `Backlog` column links to `docs/backlog.md`. Entries marked
**enforced** are pinned by a named test in `tests/unit/` or
`tests/integration/`, cited in the coverage report
([11-coverage.md](11-coverage.md)); **review** entries are asserted in code
review or carried by the backlog, with the gap named in the coverage report.

Every safety constraint (SC-1 .. SC-8) now has at least one **enforced** derived
requirement; the coverage report traces each loss to the requirement that
mitigates it.

| ID | Requirement | From | Backlog | ADR | Status |
|----|-------------|------|---------|-----|--------|
| DR-1 | The self-model derives its `p5`/`p50`/`p95` band by Monte Carlo over the estimator posterior, so the band widens and the numeric `confidence` (in [0, 1]) falls as estimator covariance grows. There is no separate `confidence_low` flag; low confidence is the low end of the numeric scale. | SC-1 | BL-035 | ADR-0010 | **enforced** |
| DR-2 | `state_transition` refuses entry into an operational mode when the thermal subsystem's reported `headroom_c` is below the profile threshold, through the `SafetyEnforcer` gate. The gate fails closed on missing context. | SC-2 | BL-014, BL-022 | ADR-0001, ADR-0018, ADR-0022 | **enforced** |
| DR-3 | The comms state derivation returns `LIMITED` (or `DENIED`) rather than `CONNECTED` when a link's loss or throughput is outside the healthy envelope; this is the label the FSM and the adapters consume. | SC-3 | BL-012, BL-030 | ADR-0010 | **enforced** |
| DR-4 | Every adapter's `encode` includes the source timestamp and refuses to encode if the underlying estimate is older than the adapter's `max_age` (`assert_fresh`). JSON adapters refuse decode payloads larger than `max_payload_len`. | SC-4 | BL-024..BL-036 | ADR-0011 | **enforced** |
| DR-5 | `inference_cloud` returns a structured `CapExhausted` payload, the `InferenceFallback` ladder routes to the local mock on cloud failure, and `AnthropicClient.call` is bounded by `timeout_s`. | SC-5 | BL-021 | ADR-0005 | **enforced** |
| DR-6 | The audit handler uses `WatchedFileHandler` and fsyncs after every emit; a failed fsync marks the handler degraded. The systemd `ExecStop` and the daily flush timer call `nous flush`, which checkpoints the SQLite WAL and fsyncs the audit handler. | SC-6 | BL-038 | ADR-0002, ADR-0008 | **enforced** |
| DR-7 | The OAuth issuer defaults to `single_client=true` and a re-registration evicts the prior client, so an unintended second client cannot silently co-exist. Disabling lockdown requires an ADR; the disable-time startup warning is an observability add-on (the one part not pinned by a test). | SC-7 | BL-019 | ADR-0008 | **enforced** |
| DR-8 | `CallCap.increment` fails closed (raises `CapExhausted`) on a corrupted persistence file or a failed fsync. Concurrent writers cannot race the truncate/write window. | SC-5 | BL-021 | ADR-0005 | **enforced** |
| DR-9 | The policy classifier's additive-surface rule defaults unknown tools to `STATEFUL`, so guarded mode refuses them without an explicit allow regex and readonly mode refuses them outright. | SC-7, additive-surface | BL-038 | ADR-0007 | **enforced** |
| DR-10 | The position and biometric Kalman filters validate inputs; NaN, Inf, and out-of-range observations are rejected (incrementing `rejected_updates`) without poisoning the central estimate. | SC-1 | BL-026, BL-029 | ADR-0010 | **enforced** |
| DR-11 | `state_transition` refuses entry into an operational mode when the power subsystem's reported `soc_pct` is below the profile's critical reserve (`power.soc_pct_critical_threshold`), through the same `SafetyEnforcer` gate as DR-2 and failing closed the same way. The `recover`/`cool` exits out of an impaired mode stay gated, so the device cannot leave an impaired posture until reserve is restored. | SC-8 | BL-022 | ADR-0018, ADR-0022, ADR-0029 | **enforced** |
| DR-12 | The audit JSONL is a per-record hash chain: each line commits to its predecessor, so `verify_chain` (the `audit_verify` tool) locates the first mutation, mid-stream deletion, insertion, or reorder. A daily anchor pins the chain head once per UTC day into a separate append-only file, and `verify_anchors` (the `audit_anchor_verify` tool) detects tail truncation within the retention window. | SC-6 | BL-016, BL-031 | ADR-0025, ADR-0026 | **enforced** |
| DR-13 | The engine auto-safes each tick: on a sustained SC-2 (thermal) or SC-8 (power) violation, or a debounced operator `INCAPACITATED` label, `Engine._auto_safe` drives the FSM one step toward a safer mode through the same enforcer, mirrored to the audit log under `Tier.SAFETY`. This covers the "sustains" clause of H-2 / H-8: a mode that becomes unsafe after entry is exited, not only refused at entry. | SC-2, SC-8 | BL-022 | ADR-0027, ADR-0028, ADR-0029 | **enforced** |
| DR-14 | The failsafe edges are reachable and ungated: every operational or impaired mode reaches `SAFE` in one `safe` trigger, and the terminal `FAULT` is reachable in one `fault` trigger from every powered mode. No `safe` or `fault` edge is gated, so a path to safety is never refused. | SC-2, SC-8 | BL-022 | ADR-0028, ADR-0030 | **enforced** |
