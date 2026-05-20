# 05 -- Safety constraints

| ID | Constraint | Addresses |
|----|------------|-----------|
| SC-1 | The self-model must derive its quantiles from estimator covariance and explicitly mark a claim as low-confidence when the estimator has diverged. | H-1 |
| SC-2 | The state machine must refuse a `MISSION` transition when the thermal estimator reports `headroom < threshold`. The threshold lives in the hardware profile. | H-2 |
| SC-3 | The comms estimator must mark a link as `LIMITED` rather than `CONNECTED` whenever the loss or throughput estimator is outside the healthy envelope. | H-3 |
| SC-4 | Interop adapters must include the source timestamp on every encoded message and refuse to encode if the underlying estimate is older than the adapter's `max_age`. | H-4 |
| SC-5 | `inference_cloud` must fail closed with `CapExhausted` when the daily cap is reached, surfacing the failure to the controller. | H-5 |
| SC-6 | The audit log must be rotated by `logrotate` with `postrotate chattr +a` (or equivalent). The audit handler must use `WatchedFileHandler` so rotation does not break the descriptor. | H-6 |
| SC-7 | The OAuth issuer must default to `single_client=true`. Disabling single-client lockdown requires an ADR. | H-7 |
