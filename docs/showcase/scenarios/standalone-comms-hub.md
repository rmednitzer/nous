# Scenario: standalone-comms-hub

Unit acts as the comms hub for a multi-radio environment.

## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 720 |
| tick rate | 0.0166667 Hz |
| name | standalone-comms-hub |
| source | `scenarios/standalone-comms-hub.yaml` |

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
| position | `parametric` | dead reckoning + GNSS fix gating; EKF passthrough (full EKF is BL-026) |
| biometrics | `filtered` | HR / core temp / hydration / cognitive load with multi-channel Kalman |
| comms | `parametric` | per-link envelopes drive FSM each tick; particle filter is BL-030 |
| inference | `parametric` | local-path with profile-derived latency / energy / capacity |

## Final state

- mode: `idle`
- operator: `nominal`
- comms: `denied`
- SoC: 82.013 %
- APU offered: 0.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@@%%%%%%#####*******+++++======------......___`
- APU offered (W): `++++++++++++++++++++++++++++++++++++++++++++++++`

## Sampled snapshots

| tick | t (s) | mode | SoC % | APU W | fuel % |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 60 | `relay` | 99.976 | 0.000 | 100.000 |
| 12 | 720 | `relay` | 99.708 | 0.000 | 100.000 |
| 24 | 1440 | `relay` | 99.415 | 0.000 | 100.000 |
| 36 | 2160 | `relay` | 99.123 | 0.000 | 100.000 |
| 48 | 2880 | `relay` | 98.830 | 0.000 | 100.000 |
| 60 | 3600 | `relay` | 98.537 | 0.000 | 100.000 |
| 72 | 4320 | `relay` | 98.243 | 0.000 | 100.000 |
| 84 | 5040 | `relay` | 97.950 | 0.000 | 100.000 |
| 96 | 5760 | `relay` | 97.656 | 0.000 | 100.000 |
| 108 | 6480 | `relay` | 97.362 | 0.000 | 100.000 |
| 120 | 7200 | `relay` | 97.067 | 0.000 | 100.000 |
| 132 | 7920 | `relay` | 96.773 | 0.000 | 100.000 |
| 144 | 8640 | `relay` | 96.478 | 0.000 | 100.000 |
| 156 | 9360 | `relay` | 96.182 | 0.000 | 100.000 |
| 168 | 10080 | `relay` | 95.887 | 0.000 | 100.000 |
| 180 | 10800 | `relay` | 95.591 | 0.000 | 100.000 |
| 192 | 11520 | `relay` | 95.295 | 0.000 | 100.000 |
| 204 | 12240 | `relay` | 94.999 | 0.000 | 100.000 |
| 216 | 12960 | `relay` | 94.703 | 0.000 | 100.000 |
| 228 | 13680 | `relay` | 94.406 | 0.000 | 100.000 |
| 240 | 14400 | `relay` | 94.109 | 0.000 | 100.000 |
| 252 | 15120 | `relay` | 93.812 | 0.000 | 100.000 |
| 264 | 15840 | `relay` | 93.515 | 0.000 | 100.000 |
| 276 | 16560 | `relay` | 93.217 | 0.000 | 100.000 |
| 288 | 17280 | `relay` | 92.919 | 0.000 | 100.000 |
| 300 | 18000 | `relay` | 92.621 | 0.000 | 100.000 |
| 312 | 18720 | `relay` | 92.322 | 0.000 | 100.000 |
| 324 | 19440 | `relay` | 92.023 | 0.000 | 100.000 |
| 336 | 20160 | `relay` | 91.724 | 0.000 | 100.000 |
| 348 | 20880 | `relay` | 91.425 | 0.000 | 100.000 |
| 360 | 21600 | `relay` | 91.126 | 0.000 | 100.000 |
| 372 | 22320 | `relay` | 90.826 | 0.000 | 100.000 |
| 384 | 23040 | `relay` | 90.526 | 0.000 | 100.000 |
| 396 | 23760 | `relay` | 90.225 | 0.000 | 100.000 |
| 408 | 24480 | `relay` | 89.925 | 0.000 | 100.000 |
| 420 | 25200 | `relay` | 89.624 | 0.000 | 100.000 |
| 432 | 25920 | `relay` | 89.323 | 0.000 | 100.000 |
| 444 | 26640 | `relay` | 89.021 | 0.000 | 100.000 |
| 456 | 27360 | `relay` | 88.720 | 0.000 | 100.000 |
| 468 | 28080 | `relay` | 88.418 | 0.000 | 100.000 |
| 480 | 28800 | `relay` | 88.115 | 0.000 | 100.000 |
| 492 | 29520 | `relay` | 87.813 | 0.000 | 100.000 |
| 504 | 30240 | `relay` | 87.510 | 0.000 | 100.000 |
| 516 | 30960 | `relay` | 87.207 | 0.000 | 100.000 |
| 528 | 31680 | `relay` | 86.904 | 0.000 | 100.000 |
| 540 | 32400 | `relay` | 86.600 | 0.000 | 100.000 |
| 552 | 33120 | `relay` | 86.296 | 0.000 | 100.000 |
| 564 | 33840 | `relay` | 85.992 | 0.000 | 100.000 |
| 576 | 34560 | `relay` | 85.688 | 0.000 | 100.000 |
| 588 | 35280 | `relay` | 85.383 | 0.000 | 100.000 |
| 600 | 36000 | `idle` | 85.078 | 0.000 | 100.000 |
| 612 | 36720 | `idle` | 84.773 | 0.000 | 100.000 |
| 624 | 37440 | `idle` | 84.467 | 0.000 | 100.000 |
| 636 | 38160 | `idle` | 84.162 | 0.000 | 100.000 |
| 648 | 38880 | `idle` | 83.855 | 0.000 | 100.000 |
| 660 | 39600 | `idle` | 83.549 | 0.000 | 100.000 |
| 672 | 40320 | `idle` | 83.242 | 0.000 | 100.000 |
| 684 | 41040 | `idle` | 82.936 | 0.000 | 100.000 |
| 696 | 41760 | `idle` | 82.628 | 0.000 | 100.000 |
| 708 | 42480 | `idle` | 82.321 | 0.000 | 100.000 |
| 720 | 43200 | `idle` | 82.013 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=relay) | applied: mode -> relay |
| 30 | `inject_comms_loss` (link_id=tak, loss_pct=20) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 60 | `inject_comms_loss` (link_id=lora, loss_pct=10) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 600 | `state_transition` (trigger=complete) | applied: mode -> idle |

## Artefacts

- raw JSONL: [`standalone-comms-hub.jsonl`](../data/standalone-comms-hub.jsonl)
