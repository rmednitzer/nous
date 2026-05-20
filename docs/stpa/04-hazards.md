# 04 -- Hazards

| ID | Hazard | Linked losses |
|----|--------|---------------|
| H-1 | The self-model publishes a capability claim whose confidence is not supported by the estimator's covariance. | L-1 |
| H-2 | The state machine permits a transition into `MISSION` while the thermal estimator is above the headroom threshold. | L-2 |
| H-3 | The comms estimator labels a link as `CONNECTED` while the underlying simulator state has degraded it. | L-1, L-3 |
| H-4 | An interop adapter encodes a message from a stale or partial estimate (e.g. a CoT message with the last-known position long after position has diverged). | L-3 |
| H-5 | The Anthropic call cap is exhausted in the middle of a scenario, and the controller does not fail over to `inference_local`. | L-2 |
| H-6 | The audit log is rotated in a way that breaks the append-only property (e.g. without `chattr +a`). | L-4 |
| H-7 | The OAuth issuer admits a client without single-client lockdown enforced, exposing the tool surface to an unintended party. | L-2, L-3 |
