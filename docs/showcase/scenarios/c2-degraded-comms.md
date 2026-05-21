# Scenario: c2-degraded-comms

Command-and-control loop with intermittent LTE blackout.

## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 720 |
| tick rate | 0.0166667 Hz |
| name | c2-degraded-comms |
| source | `scenarios/c2-degraded-comms.yaml` |

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

- mode: `mission`
- operator: `nominal`
- comms: `connected`
- SoC: 85.693 %
- APU offered: 0.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@@%%%%%%#####*******+++++======------......___`
- APU offered (W): `++++++++++++++++++++++++++++++++++++++++++++++++`

## Sampled snapshots

| tick | t (s) | mode | SoC % | APU W | fuel % |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 60 | `c2` | 99.981 | 0.000 | 100.000 |
| 12 | 720 | `c2` | 99.766 | 0.000 | 100.000 |
| 24 | 1440 | `c2` | 99.533 | 0.000 | 100.000 |
| 36 | 2160 | `c2` | 99.299 | 0.000 | 100.000 |
| 48 | 2880 | `degraded` | 99.065 | 0.000 | 100.000 |
| 60 | 3600 | `mission` | 98.830 | 0.000 | 100.000 |
| 72 | 4320 | `mission` | 98.596 | 0.000 | 100.000 |
| 84 | 5040 | `mission` | 98.361 | 0.000 | 100.000 |
| 96 | 5760 | `mission` | 98.127 | 0.000 | 100.000 |
| 108 | 6480 | `mission` | 97.892 | 0.000 | 100.000 |
| 120 | 7200 | `mission` | 97.657 | 0.000 | 100.000 |
| 132 | 7920 | `mission` | 97.421 | 0.000 | 100.000 |
| 144 | 8640 | `mission` | 97.186 | 0.000 | 100.000 |
| 156 | 9360 | `mission` | 96.950 | 0.000 | 100.000 |
| 168 | 10080 | `mission` | 96.715 | 0.000 | 100.000 |
| 180 | 10800 | `mission` | 96.479 | 0.000 | 100.000 |
| 192 | 11520 | `mission` | 96.243 | 0.000 | 100.000 |
| 204 | 12240 | `mission` | 96.007 | 0.000 | 100.000 |
| 216 | 12960 | `mission` | 95.770 | 0.000 | 100.000 |
| 228 | 13680 | `mission` | 95.534 | 0.000 | 100.000 |
| 240 | 14400 | `mission` | 95.297 | 0.000 | 100.000 |
| 252 | 15120 | `mission` | 95.060 | 0.000 | 100.000 |
| 264 | 15840 | `mission` | 94.823 | 0.000 | 100.000 |
| 276 | 16560 | `mission` | 94.586 | 0.000 | 100.000 |
| 288 | 17280 | `mission` | 94.349 | 0.000 | 100.000 |
| 300 | 18000 | `mission` | 94.111 | 0.000 | 100.000 |
| 312 | 18720 | `mission` | 93.874 | 0.000 | 100.000 |
| 324 | 19440 | `mission` | 93.636 | 0.000 | 100.000 |
| 336 | 20160 | `mission` | 93.398 | 0.000 | 100.000 |
| 348 | 20880 | `mission` | 93.160 | 0.000 | 100.000 |
| 360 | 21600 | `mission` | 92.921 | 0.000 | 100.000 |
| 372 | 22320 | `mission` | 92.683 | 0.000 | 100.000 |
| 384 | 23040 | `mission` | 92.444 | 0.000 | 100.000 |
| 396 | 23760 | `mission` | 92.205 | 0.000 | 100.000 |
| 408 | 24480 | `mission` | 91.966 | 0.000 | 100.000 |
| 420 | 25200 | `mission` | 91.727 | 0.000 | 100.000 |
| 432 | 25920 | `mission` | 91.488 | 0.000 | 100.000 |
| 444 | 26640 | `mission` | 91.249 | 0.000 | 100.000 |
| 456 | 27360 | `mission` | 91.009 | 0.000 | 100.000 |
| 468 | 28080 | `mission` | 90.769 | 0.000 | 100.000 |
| 480 | 28800 | `mission` | 90.529 | 0.000 | 100.000 |
| 492 | 29520 | `mission` | 90.289 | 0.000 | 100.000 |
| 504 | 30240 | `mission` | 90.049 | 0.000 | 100.000 |
| 516 | 30960 | `mission` | 89.808 | 0.000 | 100.000 |
| 528 | 31680 | `mission` | 89.567 | 0.000 | 100.000 |
| 540 | 32400 | `mission` | 89.327 | 0.000 | 100.000 |
| 552 | 33120 | `mission` | 89.086 | 0.000 | 100.000 |
| 564 | 33840 | `mission` | 88.844 | 0.000 | 100.000 |
| 576 | 34560 | `mission` | 88.603 | 0.000 | 100.000 |
| 588 | 35280 | `mission` | 88.361 | 0.000 | 100.000 |
| 600 | 36000 | `mission` | 88.120 | 0.000 | 100.000 |
| 612 | 36720 | `mission` | 87.878 | 0.000 | 100.000 |
| 624 | 37440 | `mission` | 87.636 | 0.000 | 100.000 |
| 636 | 38160 | `mission` | 87.394 | 0.000 | 100.000 |
| 648 | 38880 | `mission` | 87.151 | 0.000 | 100.000 |
| 660 | 39600 | `mission` | 86.909 | 0.000 | 100.000 |
| 672 | 40320 | `mission` | 86.666 | 0.000 | 100.000 |
| 684 | 41040 | `mission` | 86.423 | 0.000 | 100.000 |
| 696 | 41760 | `mission` | 86.180 | 0.000 | 100.000 |
| 708 | 42480 | `mission` | 85.937 | 0.000 | 100.000 |
| 720 | 43200 | `mission` | 85.693 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=c2) | applied: mode -> c2 |
| 10 | `inject_comms_loss` (link_id=lte, loss_pct=60) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 18 | `inject_comms_loss` (link_id=lte, loss_pct=0) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 35 | `inject_comms_loss` (link_id=lte, loss_pct=100) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 40 | `state_transition` (trigger=degrade) | applied: mode -> degraded |
| 55 | `inject_comms_loss` (link_id=lte, loss_pct=0) | skipped: action 'inject_comms_loss' not yet wired (BL-014) |
| 56 | `state_transition` (trigger=recover) | applied: mode -> mission |

## Artefacts

- raw JSONL: [`c2-degraded-comms.jsonl`](../data/c2-degraded-comms.jsonl)
