# 08 -- Loss scenarios

Each scenario links the unsafe control action (UCA, artefact 07) or the named
causal factor that realises it, and the loss it leads to. LS-4 and LS-5 do not
originate in a controller UCA; they are deployment / configuration faults inside
the system boundary (see the note in artefact 07 and
[11-coverage.md](11-coverage.md)).

| ID | Scenario | UCA / cause | Loss |
|----|----------|-------------|------|
| LS-1 | The thermal estimator's covariance grows during a heat-soak; the self-model still reports the central estimate without widening its p95 quantile. The controller acts on the central estimate and pushes the simulator into `MISSION` past the headroom threshold. | UCA-1a | L-1, L-2 |
| LS-2 | The comms estimator's particle filter converges on `CONNECTED` while the link's actual loss is climbing. The controller publishes a CoT message; the downstream TAK server learns of the unit's position from a link that has already gone away. | UCA-2a | L-3 |
| LS-3 | A long scenario exhausts the Anthropic daily cap. The controller's next call returns `CapExhausted`. Because the controller does not consult `device_info` for cap state, the failure is treated as a transient error and retried. The simulator stays in `MISSION` past the safe envelope. | UCA-3a | L-1, L-2 |
| LS-4 | `logrotate` runs without `chattr +a`. The post-rotate audit file is writable; an attacker or a buggy script edits a record. With the BL-016 hash chain the edit breaks the chain at that record, which `audit_verify` reports (DR-12); without it the tamper would be silent. | audit rotation (deployment fault) | L-4 |
| LS-5 | A second OAuth client registers because single-client lockdown was disabled for debugging. The lockdown is not re-enabled. The second client drives the simulator into a posture the operator did not intend. | OAuth misconfig (config fault) | L-2, L-3 |
