# Scenario: relay-mountain

Unit set down on a ridge as a comms relay; thermal soak during sun.

## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 1440 |
| tick rate | 0.0166667 Hz |
| name | relay-mountain |
| source | `scenarios/relay-mountain.yaml` |

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

- mode: `degraded`
- operator: `nominal`
- comms: `denied`
- SoC: 62.99 %
- APU offered: 0.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@@%%%%%%######******++++++=====------......___`
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
| 732 | 43920 | `degraded` | 81.705 | 0.000 | 100.000 |
| 744 | 44640 | `degraded` | 81.397 | 0.000 | 100.000 |
| 756 | 45360 | `degraded` | 81.088 | 0.000 | 100.000 |
| 768 | 46080 | `degraded` | 80.779 | 0.000 | 100.000 |
| 780 | 46800 | `degraded` | 80.470 | 0.000 | 100.000 |
| 792 | 47520 | `degraded` | 80.160 | 0.000 | 100.000 |
| 804 | 48240 | `degraded` | 79.850 | 0.000 | 100.000 |
| 816 | 48960 | `degraded` | 79.540 | 0.000 | 100.000 |
| 828 | 49680 | `degraded` | 79.230 | 0.000 | 100.000 |
| 840 | 50400 | `degraded` | 78.919 | 0.000 | 100.000 |
| 852 | 51120 | `degraded` | 78.608 | 0.000 | 100.000 |
| 864 | 51840 | `degraded` | 78.297 | 0.000 | 100.000 |
| 876 | 52560 | `degraded` | 77.985 | 0.000 | 100.000 |
| 888 | 53280 | `degraded` | 77.673 | 0.000 | 100.000 |
| 900 | 54000 | `degraded` | 77.361 | 0.000 | 100.000 |
| 912 | 54720 | `degraded` | 77.049 | 0.000 | 100.000 |
| 924 | 55440 | `degraded` | 76.736 | 0.000 | 100.000 |
| 936 | 56160 | `degraded` | 76.423 | 0.000 | 100.000 |
| 948 | 56880 | `degraded` | 76.110 | 0.000 | 100.000 |
| 960 | 57600 | `degraded` | 75.796 | 0.000 | 100.000 |
| 972 | 58320 | `degraded` | 75.482 | 0.000 | 100.000 |
| 984 | 59040 | `degraded` | 75.168 | 0.000 | 100.000 |
| 996 | 59760 | `degraded` | 74.853 | 0.000 | 100.000 |
| 1008 | 60480 | `degraded` | 74.538 | 0.000 | 100.000 |
| 1020 | 61200 | `degraded` | 74.223 | 0.000 | 100.000 |
| 1032 | 61920 | `degraded` | 73.907 | 0.000 | 100.000 |
| 1044 | 62640 | `degraded` | 73.592 | 0.000 | 100.000 |
| 1056 | 63360 | `degraded` | 73.275 | 0.000 | 100.000 |
| 1068 | 64080 | `degraded` | 72.959 | 0.000 | 100.000 |
| 1080 | 64800 | `degraded` | 72.642 | 0.000 | 100.000 |
| 1092 | 65520 | `degraded` | 72.325 | 0.000 | 100.000 |
| 1104 | 66240 | `degraded` | 72.008 | 0.000 | 100.000 |
| 1116 | 66960 | `degraded` | 71.690 | 0.000 | 100.000 |
| 1128 | 67680 | `degraded` | 71.372 | 0.000 | 100.000 |
| 1140 | 68400 | `degraded` | 71.054 | 0.000 | 100.000 |
| 1152 | 69120 | `degraded` | 70.735 | 0.000 | 100.000 |
| 1164 | 69840 | `degraded` | 70.416 | 0.000 | 100.000 |
| 1176 | 70560 | `degraded` | 70.097 | 0.000 | 100.000 |
| 1188 | 71280 | `degraded` | 69.777 | 0.000 | 100.000 |
| 1200 | 72000 | `degraded` | 69.457 | 0.000 | 100.000 |
| 1212 | 72720 | `degraded` | 69.137 | 0.000 | 100.000 |
| 1224 | 73440 | `degraded` | 68.816 | 0.000 | 100.000 |
| 1236 | 74160 | `degraded` | 68.496 | 0.000 | 100.000 |
| 1248 | 74880 | `degraded` | 68.174 | 0.000 | 100.000 |
| 1260 | 75600 | `degraded` | 67.853 | 0.000 | 100.000 |
| 1272 | 76320 | `degraded` | 67.531 | 0.000 | 100.000 |
| 1284 | 77040 | `degraded` | 67.209 | 0.000 | 100.000 |
| 1296 | 77760 | `degraded` | 66.886 | 0.000 | 100.000 |
| 1308 | 78480 | `degraded` | 66.563 | 0.000 | 100.000 |
| 1320 | 79200 | `degraded` | 66.240 | 0.000 | 100.000 |
| 1332 | 79920 | `degraded` | 65.917 | 0.000 | 100.000 |
| 1344 | 80640 | `degraded` | 65.593 | 0.000 | 100.000 |
| 1356 | 81360 | `degraded` | 65.269 | 0.000 | 100.000 |
| 1368 | 82080 | `degraded` | 64.944 | 0.000 | 100.000 |
| 1380 | 82800 | `degraded` | 64.619 | 0.000 | 100.000 |
| 1392 | 83520 | `degraded` | 64.294 | 0.000 | 100.000 |
| 1404 | 84240 | `degraded` | 63.968 | 0.000 | 100.000 |
| 1416 | 84960 | `degraded` | 63.643 | 0.000 | 100.000 |
| 1428 | 85680 | `degraded` | 63.316 | 0.000 | 100.000 |
| 1440 | 86400 | `degraded` | 62.990 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=relay) | applied: mode -> relay |
| 120 | `inject_thermal` (ambient_delta_c=12) | skipped: action 'inject_thermal' not yet wired (BL-014) |
| 240 | `inject_thermal` (ambient_delta_c=0) | skipped: action 'inject_thermal' not yet wired (BL-014) |
| 1200 | `state_transition` (trigger=complete) | refused: no transition from 'degraded' on trigger 'complete' |

## Artefacts

- raw JSONL: [`relay-mountain.jsonl`](../data/relay-mountain.jsonl)
