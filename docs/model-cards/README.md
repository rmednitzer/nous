# Model cards

A model card documents what a model claims, what it costs, and where
it breaks. The cards below cover the v0.1 estimators and the local
inference mock. Each card answers the same questions:

- **Inputs.** What the estimator consumes.
- **Outputs.** What the estimator produces.
- **SLA.** Latency budget per update and the covariance bound the
  filter must respect.
- **Known failure modes.** Where the assumptions break.

| Subsystem / Model | Card |
|-------------------|------|
| Power subsystem (Li-ion battery) | [subsystem-power.md](subsystem-power.md) |
| APU subsystem (solar + fuel cell + vehicle + USB-C PD + hand-crank) | [subsystem-apu.md](subsystem-apu.md) |

| Estimator / Model | Card |
|-------------------|------|
| Position EKF | [estimator-position-ekf.md](estimator-position-ekf.md) |
| Power SoC | [estimator-power-soc.md](estimator-power-soc.md) |
| APU per-source Kalman | [estimator-apu.md](estimator-apu.md) |
| Thermal Kalman | [estimator-thermal-kalman.md](estimator-thermal-kalman.md) |
| Biometrics Kalman | [estimator-biometrics-kalman.md](estimator-biometrics-kalman.md) |
| Comms particle filter | [estimator-comms-particle.md](estimator-comms-particle.md) |
| Inference local mock | [inference-local-mock.md](inference-local-mock.md) |
