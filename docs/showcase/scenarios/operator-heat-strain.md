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

This run exercises the development-line subsystems and records the
rest as defaults. See [Fidelity](../fidelity.md) for the legend.

| Subsystem | Substance | Source |
| --- | --- | --- |
| power | `filtered` | Li-ion + Peukert + SoC Kalman |
| apu | `filtered` | solar MPPT, fuel cell, vehicle, USB-C PD; per-source Kalman |
| thermal | `filtered` | two-state lumped model; per-channel Kalman |
| compute | `filtered` | load fraction + profile-driven draw curve; per-channel Kalman |
| storage | `filtered` | NAND wear + capacity accounting; per-channel Kalman |
| sensors | `filtered` | temp / humidity / baro authoritative ambient; multi-channel Kalman |
| position | `parametric` | dead reckoning + GNSS fix gating; Kalman passthrough (IMU fusion is BL-026) |
| biometrics | `filtered` | HR / core temp / hydration / cognitive load with multi-channel Kalman |
| comms | `parametric` | per-link envelopes drive FSM each tick; particle filter is BL-030 |
| inference | `parametric` | local-path with profile-derived latency / energy / capacity |

## Final state

- mode: `safe`
- operator: `incapacitated`
- comms: `denied`
- SoC: 86.6 %
- APU offered: 0.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@%%%%%%######*****++++++======-----......___`
- APU offered (W): `++++++++++++++++++++++++++++++++++++++++++++++`

## Sampled snapshots

| tick | t (s) | mode | SoC % | APU W | fuel % |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 60 | `mission` | 99.976 | 0.000 | 100.000 |
| 12 | 720 | `mission` | 99.708 | 0.000 | 100.000 |
| 24 | 1440 | `mission` | 99.415 | 0.000 | 100.000 |
| 36 | 2160 | `mission` | 99.123 | 0.000 | 100.000 |
| 48 | 2880 | `mission` | 98.830 | 0.000 | 100.000 |
| 60 | 3600 | `mission` | 98.537 | 0.000 | 100.000 |
| 72 | 4320 | `safe` | 98.243 | 0.000 | 100.000 |
| 84 | 5040 | `safe` | 97.950 | 0.000 | 100.000 |
| 96 | 5760 | `safe` | 97.656 | 0.000 | 100.000 |
| 108 | 6480 | `safe` | 97.362 | 0.000 | 100.000 |
| 120 | 7200 | `safe` | 97.067 | 0.000 | 100.000 |
| 132 | 7920 | `safe` | 96.773 | 0.000 | 100.000 |
| 144 | 8640 | `safe` | 96.478 | 0.000 | 100.000 |
| 156 | 9360 | `safe` | 96.182 | 0.000 | 100.000 |
| 168 | 10080 | `safe` | 95.887 | 0.000 | 100.000 |
| 180 | 10800 | `safe` | 95.591 | 0.000 | 100.000 |
| 192 | 11520 | `safe` | 95.295 | 0.000 | 100.000 |
| 204 | 12240 | `safe` | 94.999 | 0.000 | 100.000 |
| 216 | 12960 | `safe` | 94.703 | 0.000 | 100.000 |
| 228 | 13680 | `safe` | 94.406 | 0.000 | 100.000 |
| 240 | 14400 | `safe` | 94.109 | 0.000 | 100.000 |
| 252 | 15120 | `safe` | 93.812 | 0.000 | 100.000 |
| 264 | 15840 | `safe` | 93.515 | 0.000 | 100.000 |
| 276 | 16560 | `safe` | 93.217 | 0.000 | 100.000 |
| 288 | 17280 | `safe` | 92.919 | 0.000 | 100.000 |
| 300 | 18000 | `safe` | 92.621 | 0.000 | 100.000 |
| 312 | 18720 | `safe` | 92.322 | 0.000 | 100.000 |
| 324 | 19440 | `safe` | 92.023 | 0.000 | 100.000 |
| 336 | 20160 | `safe` | 91.724 | 0.000 | 100.000 |
| 348 | 20880 | `safe` | 91.425 | 0.000 | 100.000 |
| 360 | 21600 | `safe` | 91.126 | 0.000 | 100.000 |
| 372 | 22320 | `safe` | 90.826 | 0.000 | 100.000 |
| 384 | 23040 | `safe` | 90.526 | 0.000 | 100.000 |
| 396 | 23760 | `safe` | 90.225 | 0.000 | 100.000 |
| 408 | 24480 | `safe` | 89.925 | 0.000 | 100.000 |
| 420 | 25200 | `safe` | 89.624 | 0.000 | 100.000 |
| 432 | 25920 | `safe` | 89.323 | 0.000 | 100.000 |
| 444 | 26640 | `safe` | 89.021 | 0.000 | 100.000 |
| 456 | 27360 | `safe` | 88.720 | 0.000 | 100.000 |
| 468 | 28080 | `safe` | 88.418 | 0.000 | 100.000 |
| 480 | 28800 | `safe` | 88.115 | 0.000 | 100.000 |
| 492 | 29520 | `safe` | 87.813 | 0.000 | 100.000 |
| 504 | 30240 | `safe` | 87.510 | 0.000 | 100.000 |
| 516 | 30960 | `safe` | 87.207 | 0.000 | 100.000 |
| 528 | 31680 | `safe` | 86.904 | 0.000 | 100.000 |
| 540 | 32400 | `safe` | 86.600 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=mission) | applied: mode -> mission |
| 15 | `inject_biometrics` (core_temp_c_delta=0.5, heart_rate_bpm_delta=20) | applied: heart_rate_bpm=90.0, core_temp_c=37.5 |
| 30 | `inject_biometrics` (core_temp_c_delta=1.2, heart_rate_bpm_delta=40) | applied: heart_rate_bpm=130.0, core_temp_c=38.7 |
| 60 | `inject_biometrics` (core_temp_c_delta=2.0, heart_rate_bpm_delta=60) | applied: heart_rate_bpm=190.0, core_temp_c=40.7 |
| 90 | `state_transition` (trigger=degrade) | skipped: no transition from 'safe' on trigger 'degrade' |

## Artefacts

- raw JSONL: [`operator-heat-strain.jsonl`](../data/operator-heat-strain.jsonl)
