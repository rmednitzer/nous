# Scenario: operator-heat-strain

Operator exposure to heat causes biometrics drift; self-model should escalate OperatorState.

## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 540 |
| tick rate | 0.0166667 Hz |
| name | operator-heat-strain |
| source | `scenarios/operator-heat-strain.yaml` |

## Fidelity

This run exercises the v0.1 substantive subsystems and records the
rest as defaults. See [Fidelity](../fidelity.md) for the legend.

| Subsystem | Substance | Source |
| --- | --- | --- |
| power | `filtered` | Li-ion + Peukert + SoC Kalman |
| apu | `filtered` | solar MPPT, fuel cell, vehicle, USB-C PD; per-source Kalman |
| thermal | `stub` | ambient default; no dynamics yet |
| compute | `stub` | idle draw only; no load curve coupling yet |
| comms | `stub` | nominal `CONNECTED`; no link envelope yet |
| inference | `planned` | not exercised in v0.1 telemetry |

## Final state

- mode: `degraded`
- operator: `nominal`
- comms: `connected`
- SoC: 89.327 %
- APU offered: 0.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@%%%%%%######*****++++++======-----......___`
- APU offered (W): `++++++++++++++++++++++++++++++++++++++++++++++`

## Sampled snapshots

| tick | t (s) | mode | SoC % | APU W | fuel % |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 60 | `mission` | 99.981 | 0.000 | 100.000 |
| 12 | 720 | `mission` | 99.766 | 0.000 | 100.000 |
| 24 | 1440 | `mission` | 99.533 | 0.000 | 100.000 |
| 36 | 2160 | `mission` | 99.299 | 0.000 | 100.000 |
| 48 | 2880 | `mission` | 99.065 | 0.000 | 100.000 |
| 60 | 3600 | `mission` | 98.830 | 0.000 | 100.000 |
| 72 | 4320 | `mission` | 98.596 | 0.000 | 100.000 |
| 84 | 5040 | `mission` | 98.361 | 0.000 | 100.000 |
| 96 | 5760 | `degraded` | 98.127 | 0.000 | 100.000 |
| 108 | 6480 | `degraded` | 97.892 | 0.000 | 100.000 |
| 120 | 7200 | `degraded` | 97.657 | 0.000 | 100.000 |
| 132 | 7920 | `degraded` | 97.421 | 0.000 | 100.000 |
| 144 | 8640 | `degraded` | 97.186 | 0.000 | 100.000 |
| 156 | 9360 | `degraded` | 96.950 | 0.000 | 100.000 |
| 168 | 10080 | `degraded` | 96.715 | 0.000 | 100.000 |
| 180 | 10800 | `degraded` | 96.479 | 0.000 | 100.000 |
| 192 | 11520 | `degraded` | 96.243 | 0.000 | 100.000 |
| 204 | 12240 | `degraded` | 96.007 | 0.000 | 100.000 |
| 216 | 12960 | `degraded` | 95.770 | 0.000 | 100.000 |
| 228 | 13680 | `degraded` | 95.534 | 0.000 | 100.000 |
| 240 | 14400 | `degraded` | 95.297 | 0.000 | 100.000 |
| 252 | 15120 | `degraded` | 95.060 | 0.000 | 100.000 |
| 264 | 15840 | `degraded` | 94.823 | 0.000 | 100.000 |
| 276 | 16560 | `degraded` | 94.586 | 0.000 | 100.000 |
| 288 | 17280 | `degraded` | 94.349 | 0.000 | 100.000 |
| 300 | 18000 | `degraded` | 94.111 | 0.000 | 100.000 |
| 312 | 18720 | `degraded` | 93.874 | 0.000 | 100.000 |
| 324 | 19440 | `degraded` | 93.636 | 0.000 | 100.000 |
| 336 | 20160 | `degraded` | 93.398 | 0.000 | 100.000 |
| 348 | 20880 | `degraded` | 93.160 | 0.000 | 100.000 |
| 360 | 21600 | `degraded` | 92.921 | 0.000 | 100.000 |
| 372 | 22320 | `degraded` | 92.683 | 0.000 | 100.000 |
| 384 | 23040 | `degraded` | 92.444 | 0.000 | 100.000 |
| 396 | 23760 | `degraded` | 92.205 | 0.000 | 100.000 |
| 408 | 24480 | `degraded` | 91.966 | 0.000 | 100.000 |
| 420 | 25200 | `degraded` | 91.727 | 0.000 | 100.000 |
| 432 | 25920 | `degraded` | 91.488 | 0.000 | 100.000 |
| 444 | 26640 | `degraded` | 91.249 | 0.000 | 100.000 |
| 456 | 27360 | `degraded` | 91.009 | 0.000 | 100.000 |
| 468 | 28080 | `degraded` | 90.769 | 0.000 | 100.000 |
| 480 | 28800 | `degraded` | 90.529 | 0.000 | 100.000 |
| 492 | 29520 | `degraded` | 90.289 | 0.000 | 100.000 |
| 504 | 30240 | `degraded` | 90.049 | 0.000 | 100.000 |
| 516 | 30960 | `degraded` | 89.808 | 0.000 | 100.000 |
| 528 | 31680 | `degraded` | 89.567 | 0.000 | 100.000 |
| 540 | 32400 | `degraded` | 89.327 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=mission) | applied: mode -> mission |
| 15 | `inject_biometrics` (core_temp_c_delta=0.5, heart_rate_bpm_delta=20) | skipped: action 'inject_biometrics' not yet wired (BL-014) |
| 30 | `inject_biometrics` (core_temp_c_delta=1.2, heart_rate_bpm_delta=40) | skipped: action 'inject_biometrics' not yet wired (BL-014) |
| 60 | `inject_biometrics` (core_temp_c_delta=2.0, heart_rate_bpm_delta=60) | skipped: action 'inject_biometrics' not yet wired (BL-014) |
| 90 | `state_transition` (trigger=degrade) | applied: mode -> degraded |

## Artefacts

- raw JSONL: [`operator-heat-strain.jsonl`](../data/operator-heat-strain.jsonl)
