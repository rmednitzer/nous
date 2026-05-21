# Scenario: env-monitoring-urban

Urban environmental monitoring loop with intermittent GNSS multipath.

## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 600 |
| tick rate | 0.0166667 Hz |
| name | env-monitoring-urban |
| source | `scenarios/env-monitoring-urban.yaml` |

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

- mode: `idle`
- operator: `nominal`
- comms: `connected`
- SoC: 88.12 %
- APU offered: 0.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@@%%%%%%######*****++++++=====------......____`
- APU offered (W): `++++++++++++++++++++++++++++++++++++++++++++++++`

## Sampled snapshots

| tick | t (s) | mode | SoC % | APU W | fuel % |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 60 | `monitoring` | 99.981 | 0.000 | 100.000 |
| 12 | 720 | `monitoring` | 99.766 | 0.000 | 100.000 |
| 24 | 1440 | `monitoring` | 99.533 | 0.000 | 100.000 |
| 36 | 2160 | `monitoring` | 99.299 | 0.000 | 100.000 |
| 48 | 2880 | `monitoring` | 99.065 | 0.000 | 100.000 |
| 60 | 3600 | `idle` | 98.830 | 0.000 | 100.000 |
| 72 | 4320 | `idle` | 98.596 | 0.000 | 100.000 |
| 84 | 5040 | `idle` | 98.361 | 0.000 | 100.000 |
| 96 | 5760 | `idle` | 98.127 | 0.000 | 100.000 |
| 108 | 6480 | `idle` | 97.892 | 0.000 | 100.000 |
| 120 | 7200 | `idle` | 97.657 | 0.000 | 100.000 |
| 132 | 7920 | `idle` | 97.421 | 0.000 | 100.000 |
| 144 | 8640 | `idle` | 97.186 | 0.000 | 100.000 |
| 156 | 9360 | `idle` | 96.950 | 0.000 | 100.000 |
| 168 | 10080 | `idle` | 96.715 | 0.000 | 100.000 |
| 180 | 10800 | `idle` | 96.479 | 0.000 | 100.000 |
| 192 | 11520 | `idle` | 96.243 | 0.000 | 100.000 |
| 204 | 12240 | `idle` | 96.007 | 0.000 | 100.000 |
| 216 | 12960 | `idle` | 95.770 | 0.000 | 100.000 |
| 228 | 13680 | `idle` | 95.534 | 0.000 | 100.000 |
| 240 | 14400 | `idle` | 95.297 | 0.000 | 100.000 |
| 252 | 15120 | `idle` | 95.060 | 0.000 | 100.000 |
| 264 | 15840 | `idle` | 94.823 | 0.000 | 100.000 |
| 276 | 16560 | `idle` | 94.586 | 0.000 | 100.000 |
| 288 | 17280 | `idle` | 94.349 | 0.000 | 100.000 |
| 300 | 18000 | `idle` | 94.111 | 0.000 | 100.000 |
| 312 | 18720 | `idle` | 93.874 | 0.000 | 100.000 |
| 324 | 19440 | `idle` | 93.636 | 0.000 | 100.000 |
| 336 | 20160 | `idle` | 93.398 | 0.000 | 100.000 |
| 348 | 20880 | `idle` | 93.160 | 0.000 | 100.000 |
| 360 | 21600 | `idle` | 92.921 | 0.000 | 100.000 |
| 372 | 22320 | `idle` | 92.683 | 0.000 | 100.000 |
| 384 | 23040 | `idle` | 92.444 | 0.000 | 100.000 |
| 396 | 23760 | `idle` | 92.205 | 0.000 | 100.000 |
| 408 | 24480 | `idle` | 91.966 | 0.000 | 100.000 |
| 420 | 25200 | `idle` | 91.727 | 0.000 | 100.000 |
| 432 | 25920 | `idle` | 91.488 | 0.000 | 100.000 |
| 444 | 26640 | `idle` | 91.249 | 0.000 | 100.000 |
| 456 | 27360 | `idle` | 91.009 | 0.000 | 100.000 |
| 468 | 28080 | `idle` | 90.769 | 0.000 | 100.000 |
| 480 | 28800 | `idle` | 90.529 | 0.000 | 100.000 |
| 492 | 29520 | `idle` | 90.289 | 0.000 | 100.000 |
| 504 | 30240 | `idle` | 90.049 | 0.000 | 100.000 |
| 516 | 30960 | `idle` | 89.808 | 0.000 | 100.000 |
| 528 | 31680 | `idle` | 89.567 | 0.000 | 100.000 |
| 540 | 32400 | `idle` | 89.327 | 0.000 | 100.000 |
| 552 | 33120 | `idle` | 89.086 | 0.000 | 100.000 |
| 564 | 33840 | `idle` | 88.844 | 0.000 | 100.000 |
| 576 | 34560 | `idle` | 88.603 | 0.000 | 100.000 |
| 588 | 35280 | `idle` | 88.361 | 0.000 | 100.000 |
| 600 | 36000 | `idle` | 88.120 | 0.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `state_transition` (trigger=monitoring) | applied: mode -> monitoring |
| 5 | `inject_sensor_drift` (source=position, lat_bias_m=4.0) | skipped: action 'inject_sensor_drift' not yet wired (BL-014) |
| 25 | `inject_sensor_drift` (source=position, lat_bias_m=0.0) | skipped: action 'inject_sensor_drift' not yet wired (BL-014) |
| 55 | `state_transition` (trigger=complete) | applied: mode -> idle |

## Artefacts

- raw JSONL: [`env-monitoring-urban.jsonl`](../data/env-monitoring-urban.jsonl)
