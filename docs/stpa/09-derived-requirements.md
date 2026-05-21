# 09 -- Derived requirements

Each row is a requirement that flows out of a safety constraint and into
the backlog. The `Backlog` column links to `docs/backlog.md`. Entries
marked **enforced** are pinned by a test in `tests/unit/` or
`tests/integration/`; the remaining entries are asserted in code review
or carried by the backlog.

| ID | Requirement | From | Backlog | ADR | Status |
|----|-------------|------|---------|-----|--------|
| DR-1 | The self-model widens its capability quantiles in proportion to estimator covariance and exposes a `confidence_low` flag when the estimator has diverged. | SC-1 | BL-035 | ADR-0010 | review |
| DR-2 | `state_transition` refuses `trigger=mission` when the thermal estimator's `headroom_c` is below the profile threshold. The FSM guard fails closed on missing context. | SC-2 | BL-014, BL-022 | ADR-0001, ADR-0010, ADR-0018 | **enforced** |
| DR-3 | The comms estimator's `state` accessor returns `LIMITED` when loss or throughput is out of envelope; this is the value that adapters consume. | SC-3 | BL-030 | ADR-0010 | review |
| DR-4 | Every adapter's `encode` includes the source timestamp and refuses to encode if the underlying estimate is older than the adapter's `max_age`. JSON adapters refuse decode payloads larger than `max_payload_len`. | SC-4 | BL-024..BL-036 | ADR-0011 | **enforced** |
| DR-5 | `inference_cloud` returns a structured `CapExhausted` payload, the `InferenceFallback` ladder routes to the local mock on cloud failure, and `AnthropicClient.call` is bounded by `timeout_s`. | SC-5 | BL-021 | ADR-0005 | **enforced** |
| DR-6 | The audit handler uses `WatchedFileHandler` and fsyncs after every emit. The systemd `ExecStop` and the daily flush timer call `nous flush`, which checkpoints the SQLite WAL and fsyncs the audit handler. | SC-6 | BL-038 | ADR-0002, ADR-0008 | **enforced** |
| DR-7 | The OAuth issuer defaults to `single_client=true`; disabling lockdown emits a startup warning and lands in the audit log. | SC-7 | BL-019 | ADR-0008 | review |
| DR-8 | `CallCap.increment` fails closed (raises `CapExhausted`) on a corrupted persistence file. Concurrent writers cannot race the truncate/write window. | SC-5 | BL-021 | ADR-0005 | **enforced** |
| DR-9 | The policy classifier's additive-surface rule defaults unknown tools to `STATEFUL`, so guarded mode refuses them without an explicit allow regex. | SC-7, additive-surface | BL-038 | ADR-0007 | **enforced** |
| DR-10 | The position EKF and biometric Kalman validate inputs; NaN, Inf, and out-of-range observations are rejected without poisoning the central estimate. | SC-1 | BL-026, BL-029 | ADR-0010 | **enforced** |
