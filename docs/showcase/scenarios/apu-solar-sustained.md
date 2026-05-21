# Scenario: apu-solar-sustained

Daytime monitoring loop sustained by the solar APU.

## Run metadata

| Field | Value |
| --- | --- |
| profile | `jetson-agx-orin` |
| tick budget | 720 |
| tick rate | 0.0166667 Hz |
| name | apu-solar-sustained |
| source | `scenarios/apu-solar-sustained.yaml` |

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
- SoC: 99.117 %
- APU offered: 5.0 W
- fuel: 100.0 %

## Series

Sparklines are over resampled buckets; high to the right is high value.

- battery SoC: `@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@#*++-._`
- APU offered (W): `@@@@@@@@@@@@@@@@@@@@@@@@================________`

## Sampled snapshots

| tick | t (s) | mode | SoC % | APU W | fuel % |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 60 | `idle` | 100.000 | 55.000 | 100.000 |
| 12 | 720 | `idle` | 100.000 | 55.000 | 100.000 |
| 24 | 1440 | `idle` | 100.000 | 55.000 | 100.000 |
| 36 | 2160 | `idle` | 100.000 | 55.000 | 100.000 |
| 48 | 2880 | `idle` | 100.000 | 55.000 | 100.000 |
| 60 | 3600 | `idle` | 100.000 | 55.000 | 100.000 |
| 72 | 4320 | `idle` | 100.000 | 55.000 | 100.000 |
| 84 | 5040 | `idle` | 100.000 | 55.000 | 100.000 |
| 96 | 5760 | `idle` | 100.000 | 55.000 | 100.000 |
| 108 | 6480 | `idle` | 100.000 | 55.000 | 100.000 |
| 120 | 7200 | `idle` | 100.000 | 55.000 | 100.000 |
| 132 | 7920 | `idle` | 100.000 | 55.000 | 100.000 |
| 144 | 8640 | `idle` | 100.000 | 55.000 | 100.000 |
| 156 | 9360 | `idle` | 100.000 | 55.000 | 100.000 |
| 168 | 10080 | `idle` | 100.000 | 55.000 | 100.000 |
| 180 | 10800 | `idle` | 100.000 | 55.000 | 100.000 |
| 192 | 11520 | `idle` | 100.000 | 55.000 | 100.000 |
| 204 | 12240 | `idle` | 100.000 | 55.000 | 100.000 |
| 216 | 12960 | `idle` | 100.000 | 55.000 | 100.000 |
| 228 | 13680 | `idle` | 100.000 | 55.000 | 100.000 |
| 240 | 14400 | `idle` | 100.000 | 55.000 | 100.000 |
| 252 | 15120 | `idle` | 100.000 | 55.000 | 100.000 |
| 264 | 15840 | `idle` | 100.000 | 55.000 | 100.000 |
| 276 | 16560 | `idle` | 100.000 | 55.000 | 100.000 |
| 288 | 17280 | `idle` | 100.000 | 55.000 | 100.000 |
| 300 | 18000 | `idle` | 100.000 | 55.000 | 100.000 |
| 312 | 18720 | `idle` | 100.000 | 55.000 | 100.000 |
| 324 | 19440 | `idle` | 100.000 | 55.000 | 100.000 |
| 336 | 20160 | `idle` | 100.000 | 55.000 | 100.000 |
| 348 | 20880 | `idle` | 100.000 | 55.000 | 100.000 |
| 360 | 21600 | `idle` | 100.000 | 25.000 | 100.000 |
| 372 | 22320 | `idle` | 100.000 | 25.000 | 100.000 |
| 384 | 23040 | `idle` | 100.000 | 25.000 | 100.000 |
| 396 | 23760 | `idle` | 100.000 | 25.000 | 100.000 |
| 408 | 24480 | `idle` | 100.000 | 25.000 | 100.000 |
| 420 | 25200 | `idle` | 100.000 | 25.000 | 100.000 |
| 432 | 25920 | `idle` | 100.000 | 25.000 | 100.000 |
| 444 | 26640 | `idle` | 100.000 | 25.000 | 100.000 |
| 456 | 27360 | `idle` | 100.000 | 25.000 | 100.000 |
| 468 | 28080 | `idle` | 100.000 | 25.000 | 100.000 |
| 480 | 28800 | `idle` | 100.000 | 25.000 | 100.000 |
| 492 | 29520 | `idle` | 100.000 | 25.000 | 100.000 |
| 504 | 30240 | `idle` | 100.000 | 25.000 | 100.000 |
| 516 | 30960 | `idle` | 100.000 | 25.000 | 100.000 |
| 528 | 31680 | `idle` | 100.000 | 25.000 | 100.000 |
| 540 | 32400 | `idle` | 100.000 | 25.000 | 100.000 |
| 552 | 33120 | `idle` | 100.000 | 25.000 | 100.000 |
| 564 | 33840 | `idle` | 100.000 | 25.000 | 100.000 |
| 576 | 34560 | `idle` | 100.000 | 25.000 | 100.000 |
| 588 | 35280 | `idle` | 100.000 | 25.000 | 100.000 |
| 600 | 36000 | `idle` | 99.993 | 5.000 | 100.000 |
| 612 | 36720 | `idle` | 99.905 | 5.000 | 100.000 |
| 624 | 37440 | `idle` | 99.818 | 5.000 | 100.000 |
| 636 | 38160 | `idle` | 99.730 | 5.000 | 100.000 |
| 648 | 38880 | `idle` | 99.642 | 5.000 | 100.000 |
| 660 | 39600 | `idle` | 99.555 | 5.000 | 100.000 |
| 672 | 40320 | `idle` | 99.467 | 5.000 | 100.000 |
| 684 | 41040 | `idle` | 99.380 | 5.000 | 100.000 |
| 696 | 41760 | `idle` | 99.292 | 5.000 | 100.000 |
| 708 | 42480 | `idle` | 99.204 | 5.000 | 100.000 |
| 720 | 43200 | `idle` | 99.117 | 5.000 | 100.000 |

## Timeline

| at_min | action | outcome |
| ---: | --- | --- |
| 0 | `inject_apu` (solar_w=55) | applied: solar_w=55 |
| 360 | `inject_apu` (solar_w=25) | applied: solar_w=25 |
| 600 | `inject_apu` (solar_w=5) | applied: solar_w=5 |

## Artefacts

- raw JSONL: [`apu-solar-sustained.jsonl`](../data/apu-solar-sustained.jsonl)
