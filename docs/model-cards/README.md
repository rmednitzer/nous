# Model cards

A model card documents what a model claims, what it costs, and where
it breaks. The cards below cover the current estimators, the local
inference mock, and the self-model capability layer. Each card answers
the same questions:

- **Inputs.** What the estimator consumes.
- **Outputs.** What the estimator produces.
- **SLA.** Latency budget per update and the covariance bound the
  filter must respect.
- **Known failure modes.** Where the assumptions break.

| Subsystem / Model | Card |
|-------------------|------|
| Power subsystem (Li-ion battery) | [subsystem-power.md](subsystem-power.md) |
| APU subsystem (solar + fuel cell + vehicle + USB-C PD) | [subsystem-apu.md](subsystem-apu.md) |
| Thermal subsystem (two-state lumped model) | [subsystem-thermal.md](subsystem-thermal.md) |
| Compute subsystem (load curve + draw) | [subsystem-compute.md](subsystem-compute.md) |
| Storage subsystem (NAND wear + capacity) | [subsystem-storage.md](subsystem-storage.md) |
| Environmental sensor subsystem (ambient ground truth) | [subsystem-sensors.md](subsystem-sensors.md) |
| Comms subsystem (per-link envelope, propagation, outbox, DTN, EMCON) | [subsystem-comms.md](subsystem-comms.md) |
| EO/IR thermo-optical subsystem (detection-range envelope) | [subsystem-eoir.md](subsystem-eoir.md) |

| Estimator / Model | Card |
|-------------------|------|
| Position (constant-velocity Kalman) | [estimator-position-kalman.md](estimator-position-kalman.md) |
| Power SoC | [estimator-power-soc.md](estimator-power-soc.md) |
| APU per-source Kalman | [estimator-apu.md](estimator-apu.md) |
| Thermal Kalman | [estimator-thermal-kalman.md](estimator-thermal-kalman.md) |
| Compute Kalman | [estimator-compute-kalman.md](estimator-compute-kalman.md) |
| Storage Kalman | [estimator-storage-kalman.md](estimator-storage-kalman.md) |
| Environmental sensor Kalman | [estimator-sensors-kalman.md](estimator-sensors-kalman.md) |
| EO/IR detection-range Kalman | [estimator-eoir-kalman.md](estimator-eoir-kalman.md) |
| Biometrics Kalman | [estimator-biometrics-kalman.md](estimator-biometrics-kalman.md) |
| Comms particle filter | [estimator-comms-particle.md](estimator-comms-particle.md) |
| Inference local mock | [inference-local-mock.md](inference-local-mock.md) |
| Self-model (capability assessment) | [self-model.md](self-model.md) |
