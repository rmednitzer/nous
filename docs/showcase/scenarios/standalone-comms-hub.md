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
| position | `parametric` | dead reckoning + GNSS fix gating; Kalman passthrough (IMU fusion is BL-061) |
| biometrics | `filtered` | HR / core temp / hydration / cognitive load with multi-channel Kalman |
| comms | `parametric` | per-link envelopes drive FSM each tick; particle filter is BL-030 |
| inference | `parametric` | local-path with profile-derived latency / energy / capacity |

## Final state

- mode: `degraded`
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
| 12 | 720 | `degraded` | 99.708 | 0.000 | 100.000 |
| 24 | 1440 | `degraded` | 99.415 | 0.000 | 100.000 |
| 36 | 2160 | `degraded` | 99.123 | 0.000 | 100.000 |
| 48 | 2880 | `degraded` | 98.830 | 0.000 | 100.000 |
| 60 | 3600 | `degraded` | 98.537 | 0.000 | 100.000 |
| 72 | 4320 | `degraded` | 98.243 | 0.000 | 100.000 |
| 84 | 5040 | `degraded` | 97.950 | 0.000 | 100.000 |
| 96 | 5760 | `degraded` | 97.656 | 0.000 | 100.000 |
| 108 | 6480 | `degraded` | 97.362 | 0.000 | 100.000 |
| 120 | 7200 | `degraded` | 97.067 | 0.000 | 100.000 |
| 132 | 7920 | `degraded` | 96.773 | 0.000 | 100.000 |
| 144 | 8640 | `degraded` | 96.478 | 0.000 | 100.000 |
| 156 | 9360 | `degraded` | 96.182 | 0.000 | 100.000 |
| 168 | 10080 | `degraded` | 95.887 | 0.000 | 100.000 |
| 180 | 10800 | `degraded` | 95.591 | 0.000 | 100.000 |
| 192 | 11520 | `degraded` | 95.295 | 0.000 | 100.000 |
| 204 | 12240 | `degraded` | 94.999 | 0.000 | 100.000 |
| 216 | 12960 | `degraded` | 94.703 | 0.000 | 100.000 |
| 228 | 13680 | `degraded` | 94.406 | 0.000 | 100.000 |
| 240 | 14400 | `degraded` | 94.109 | 0.000 | 100.000 |
| 252 | 15120 | `degraded` | 93.812 | 0.000 | 100.000 |
| 264 | 15840 | `degraded` | 93.515 | 0.000 | 100.000 |
| 276 | 16560 | `degraded` | 93.217 | 0.000 | 100.000 |
| 288 | 17280 | `degraded` | 92.919 | 0.000 | 100.000 |
| 300 | 18000 | `degraded` | 92.621 | 0.000 | 100.000 |
| 312 | 18720 | `degraded` | 92.322 | 0.000 | 100.000 |
| 324 | 19440 | `degraded` | 92.023 | 0.000 | 100.000 |
| 336 | 20160 | `degraded` | 91.724 | 0.000 | 100.000 |
| 348 | 20880 | `degraded` | 91.425 | 0.000 | 100.000 |
| 360 | 21600 | `degraded` | 91.126 | 0.000 | 100.000 |
| 372 | 22320 | `degraded` | 90.826 | 0.000 | 100.000 |
| 384 | 23040 | `degraded` | 90.526 | 0.000 | 100.000 |
| 396 | 23760 | `degraded` | 90.225 | 0.000 | 100.000 |
| 408 | 24480 | `degraded` | 89.925 | 0.000 | 100.000 |
| 420 | 25200 | `degraded` | 89.624 | 0.000 | 100.000 |
| 432 | 25920 | `degraded` | 89.323 | 0.000 | 100.000 |
| 444 | 26640 | `degraded` | 89.021 | 0.000 | 100.000 |
| 456 | 27360 | `degraded` | 88.720 | 0.000 | 100.000 |
| 468 | 28080 | `degraded` | 88.418 | 0.000 | 100.000 |
| 480 | 28800 | `degraded` | 88.115 | 0.000 | 100.000 |
| 492 | 29520 | `degraded` | 87.813 | 0.000 | 100.000 |
| 504 | 30240 | `degraded` | 87.510 | 0.000 | 100.000 |
| 516 | 30960 | `degraded` | 87.207 | 0.000 | 100.000 |
| 528 | 31680 | `degraded` | 86.904 | 0.000 | 100.000 |
| 540 | 32400 | `degraded` | 86.600 | 0.000 | 100.000 |
| 552 | 33120 | `degraded` | 86.296 | 0.000 | 100.000 |
| 564 | 33840 | `degraded` | 85.992 | 0.000 | 100.000 |
| 576 | 34560 | `degraded` | 85.688 | 0.000 | 100.000 |
| 588 | 35280 | `degraded` | 85.383 | 0.000 | 100.000 |
| 600 | 36000 | `degraded` | 85.078 | 0.000 | 100.000 |
| 612 | 36720 | `degraded` | 84.773 | 0.000 | 100.000 |
| 624 | 37440 | `degraded` | 84.467 | 0.000 | 100.000 |
| 636 | 38160 | `degraded` | 84.162 | 0.000 | 100.000 |
| 648 | 38880 | `degraded` | 83.855 | 0.000 | 100.000 |
| 660 | 39600 | `degraded` | 83.549 | 0.000 | 100.000 |
| 672 | 40320 | `degraded` | 83.242 | 0.000 | 100.000 |
| 684 | 41040 | `degraded` | 82.936 | 0.000 | 100.000 |
| 696 | 41760 | `degraded` | 82.628 | 0.000 | 100.000 |
| 708 | 42480 | `degraded` | 82.321 | 0.000 | 100.000 |
| 720 | 43200 | `degraded` | 82.013 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=relay) | applied: mode -> relay |
| 30 | `inject_comms_loss` (link_id=tak, loss_pct=20) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 60 | `inject_comms_loss` (link_id=lora, loss_pct=10) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 600 | `state_transition` (trigger=complete) | refused: no transition from 'degraded' on trigger 'complete' |

## Artefacts

- raw JSONL: [`standalone-comms-hub.jsonl`](../data/standalone-comms-hub.jsonl)
