# 09 -- Derived requirements

Each row is a requirement that flows out of a safety constraint and
into the backlog. The `Backlog` column links to `docs/backlog.md`.

| ID | Requirement | From | Backlog | ADR |
|----|-------------|------|---------|-----|
| DR-1 | The self-model widens its capability quantiles in proportion to estimator covariance and exposes a `confidence_low` flag when the estimator has diverged. | SC-1 | BL-035 | ADR-0010 |
| DR-2 | `state_transition` refuses `trigger=mission` when the thermal estimator's `headroom_c` is below the profile threshold. | SC-2 | BL-014, BL-022 | ADR-0001, ADR-0010 |
| DR-3 | The comms estimator's `state` accessor returns `LIMITED` when loss or throughput is out of envelope; this is the value that adapters consume. | SC-3 | BL-030 | ADR-0010 |
| DR-4 | Every adapter's `encode` includes the source timestamp and refuses to encode if the underlying estimate is older than the adapter's `max_age`. | SC-4 | BL-024..BL-036 | ADR-0011 |
| DR-5 | `inference_cloud` returns a structured `CapExhausted` payload (not a raw exception) and `device_info` surfaces remaining capacity so the controller can plan. | SC-5 | BL-021 | ADR-0005 |
| DR-6 | The audit handler uses `WatchedFileHandler`; the deploy bundle installs `logrotate.conf` with `postrotate chattr +a`. | SC-6 | BL-038 | ADR-0002, ADR-0008 |
| DR-7 | The OAuth issuer defaults to `single_client=true`; disabling lockdown emits a startup warning and lands in the audit log. | SC-7 | BL-019 | ADR-0008 |
