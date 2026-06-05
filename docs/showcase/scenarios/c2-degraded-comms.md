# Scenario: c2-degraded-comms

Command-and-control loop with intermittent LTE blackout. Exercises the InferenceFallback ladder: when the comms estimator reports DEGRADED or DENIED, cloud inference falls back to the local mock and the audit line records `path=local_mock` with the reason.


## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 720 |
| tick rate | 0.0166667 Hz |
| name | c2-degraded-comms |
| source | `scenarios/c2-degraded-comms.yaml` |

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
| 1 | 60 | `c2` | 99.976 | 0.000 | 100.000 |
| 12 | 720 | `degraded` | 99.708 | 0.000 | 100.000 |
| 24 | 1440 | `degraded` | 99.415 | 0.000 | 100.000 |
| 36 | 2160 | `degraded` | 99.123 | 0.000 | 100.000 |
| 48 | 2880 | `degraded` | 98.830 | 0.000 | 100.000 |
| 60 | 3600 | `idle` | 98.537 | 0.000 | 100.000 |
| 72 | 4320 | `idle` | 98.243 | 0.000 | 100.000 |
| 84 | 5040 | `idle` | 97.950 | 0.000 | 100.000 |
| 96 | 5760 | `idle` | 97.656 | 0.000 | 100.000 |
| 108 | 6480 | `idle` | 97.362 | 0.000 | 100.000 |
| 120 | 7200 | `idle` | 97.067 | 0.000 | 100.000 |
| 132 | 7920 | `idle` | 96.773 | 0.000 | 100.000 |
| 144 | 8640 | `idle` | 96.478 | 0.000 | 100.000 |
| 156 | 9360 | `idle` | 96.182 | 0.000 | 100.000 |
| 168 | 10080 | `idle` | 95.887 | 0.000 | 100.000 |
| 180 | 10800 | `idle` | 95.591 | 0.000 | 100.000 |
| 192 | 11520 | `idle` | 95.295 | 0.000 | 100.000 |
| 204 | 12240 | `idle` | 94.999 | 0.000 | 100.000 |
| 216 | 12960 | `idle` | 94.703 | 0.000 | 100.000 |
| 228 | 13680 | `idle` | 94.406 | 0.000 | 100.000 |
| 240 | 14400 | `idle` | 94.109 | 0.000 | 100.000 |
| 252 | 15120 | `idle` | 93.812 | 0.000 | 100.000 |
| 264 | 15840 | `idle` | 93.515 | 0.000 | 100.000 |
| 276 | 16560 | `idle` | 93.217 | 0.000 | 100.000 |
| 288 | 17280 | `idle` | 92.919 | 0.000 | 100.000 |
| 300 | 18000 | `idle` | 92.621 | 0.000 | 100.000 |
| 312 | 18720 | `idle` | 92.322 | 0.000 | 100.000 |
| 324 | 19440 | `idle` | 92.023 | 0.000 | 100.000 |
| 336 | 20160 | `idle` | 91.724 | 0.000 | 100.000 |
| 348 | 20880 | `idle` | 91.425 | 0.000 | 100.000 |
| 360 | 21600 | `idle` | 91.126 | 0.000 | 100.000 |
| 372 | 22320 | `idle` | 90.826 | 0.000 | 100.000 |
| 384 | 23040 | `idle` | 90.526 | 0.000 | 100.000 |
| 396 | 23760 | `idle` | 90.225 | 0.000 | 100.000 |
| 408 | 24480 | `idle` | 89.925 | 0.000 | 100.000 |
| 420 | 25200 | `idle` | 89.624 | 0.000 | 100.000 |
| 432 | 25920 | `idle` | 89.323 | 0.000 | 100.000 |
| 444 | 26640 | `idle` | 89.021 | 0.000 | 100.000 |
| 456 | 27360 | `idle` | 88.720 | 0.000 | 100.000 |
| 468 | 28080 | `idle` | 88.418 | 0.000 | 100.000 |
| 480 | 28800 | `idle` | 88.115 | 0.000 | 100.000 |
| 492 | 29520 | `idle` | 87.813 | 0.000 | 100.000 |
| 504 | 30240 | `idle` | 87.510 | 0.000 | 100.000 |
| 516 | 30960 | `idle` | 87.207 | 0.000 | 100.000 |
| 528 | 31680 | `idle` | 86.904 | 0.000 | 100.000 |
| 540 | 32400 | `idle` | 86.600 | 0.000 | 100.000 |
| 552 | 33120 | `idle` | 86.296 | 0.000 | 100.000 |
| 564 | 33840 | `idle` | 85.992 | 0.000 | 100.000 |
| 576 | 34560 | `idle` | 85.688 | 0.000 | 100.000 |
| 588 | 35280 | `idle` | 85.383 | 0.000 | 100.000 |
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
| 0 | `state_transition` (trigger=c2) | applied: mode -> c2 |
| 5 | `inference_request` (prompt=status, path=auto) | skipped: action 'inference_request' not yet wired (BL-014) |
| 10 | `inject_comms_loss` (link_id=lte, loss_pct=60) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 12 | `inference_request` (prompt=status, path=auto) | skipped: action 'inference_request' not yet wired (BL-014) |
| 18 | `inject_comms_loss` (link_id=lte, loss_pct=0) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 35 | `inject_comms_loss` (link_id=lte, loss_pct=100) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 37 | `inference_request` (prompt=fallback, path=auto) | skipped: action 'inference_request' not yet wired (BL-014) |
| 40 | `state_transition` (trigger=degrade) | refused: no transition from 'degraded' on trigger 'degrade' |
| 45 | `inference_request` (prompt=still local?, path=auto) | skipped: action 'inference_request' not yet wired (BL-014) |
| 55 | `inject_comms_loss` (link_id=lte, loss_pct=0) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 56 | `state_transition` (trigger=recover, context={'thermal_headroom_c': 25, 'thermal_headroom_threshold_c': 5}) | applied: mode -> idle |

## Artefacts

- raw JSONL: [`c2-degraded-comms.jsonl`](../data/c2-degraded-comms.jsonl)
