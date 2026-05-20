# Scenarios

A scenario is a deterministic timeline of injected events. The loader
(`src/nous/scenarios/loader.py`) parses a YAML document into a typed
`Scenario`; the injectors mutate engine state when a step fires.

## YAML shape

```yaml
schema_version: "0.1.0"
meta:
  name: env-monitoring-urban
  description: ...
profile: jetson-agx-orin
tick_budget: 600
steps:
  - at_min: 0
    action: state_transition
    args: { trigger: monitoring }
  - at_min: 30
    action: inject_thermal
    args: { delta_c: 5 }
```

## v0.1 scenarios

| File | Use case |
|------|----------|
| `scenarios/env-monitoring-urban.yaml` | Sensor-led monitoring loop. |
| `scenarios/c2-degraded-comms.yaml` | C2 with intermittent link. |
| `scenarios/relay-mountain.yaml` | Relay node on a ridge. |
| `scenarios/operator-heat-strain.yaml` | Biometrics drift under load. |
| `scenarios/standalone-comms-hub.yaml` | Unit as the comms hub. |
| `scenarios/apu-solar-sustained.yaml` | Sustained solar APU run. |
| `scenarios/apu-fuelcell-overnight.yaml` | Overnight fuel-cell run. |

Each scenario starts as a skeleton in v0.1; the injectors that mutate
engine state land with BL-014 in L1.
