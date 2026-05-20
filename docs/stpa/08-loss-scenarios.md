# 08 -- Loss scenarios

| ID | Scenario | UCA | Loss |
|----|----------|-----|------|
| LS-1 | The thermal estimator's covariance grows during a heat-soak; the self-model still reports the central estimate without widening its p95 quantile. The controller acts on the central estimate and pushes the simulator into `MISSION` past the headroom threshold. | UCA-state_transition-provided-unsafely | L-1, L-2 |
| LS-2 | The comms estimator's particle filter converges on `CONNECTED` while the link's actual loss is climbing. The controller publishes a CoT message; the downstream TAK server learns of the unit's position from a link that has already gone away. | UCA-comms_publish-provided-unsafely | L-3 |
| LS-3 | A long scenario exhausts the Anthropic daily cap. The controller's next call returns `CapExhausted`. Because the controller does not consult `device_info` for cap state, the failure is treated as a transient error and retried. The simulator stays in `MISSION` past the safe envelope. | UCA-inference_cloud-provided-unsafely | L-1, L-2 |
| LS-4 | `logrotate` runs without `chattr +a`. The post-rotate audit file is writable; an attacker (or a buggy script) edits a record. The hash of the post-edit body matches the recorded SHA-256 only by coincidence. | UCA-audit-degraded-rotation | L-4 |
| LS-5 | A second OAuth client registers because single-client lockdown was disabled for debugging. The lockdown is not re-enabled. The second client drives the simulator into a posture the operator did not intend. | UCA-oauth-misconfig | L-2, L-3 |
