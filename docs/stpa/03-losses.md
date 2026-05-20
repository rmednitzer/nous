# 03 -- Losses

The top-level losses we want the simulator to *expose* (so a controller
learns to avoid them when driving a real device):

| ID | Loss |
|----|------|
| L-1 | The controller takes an action based on a self-model claim that is more confident than the underlying estimator's covariance justifies. |
| L-2 | The controller drives the simulator into a mode (e.g. `MISSION` under elevated thermal) that the device's safety constraints should refuse. |
| L-3 | An interop adapter emits a message (CoT, MQTT publish, STANAG-labelled payload) that misrepresents the simulator's state to a downstream consumer. |
| L-4 | The audit trail loses fidelity (gap, body bytes leak, hash collision) such that an after-action review cannot reconstruct what the controller did. |
