# Model card: Thermal subsystem

**Module:** `src/nous/subsystems/thermal.py`

**Backlog:** BL-005

## Scope

A two-state lumped-capacitance model of the dominant heat path on a
passively-cooled, pack-borne appliance: heat is generated at the **junction**
(compute die), flows through a junction-to-enclosure resistance into the
**enclosure**, and dissipates from the enclosure to **ambient** through a
second resistance. Two state variables (`junction_c`, `enclosure_c`)
integrate the lumped equations forward with explicit Euler; the integrator
sub-steps internally (inner `dt <= 0.5 * C_j * R_je`) so a slow controller
tick rate stays inside the stability bound. The junction time constant is
short (seconds), the enclosure long (minutes), giving the characteristic
"quick spike then slow soak".

This subsystem is the source of the SC-2 thermal-headroom gate and the
`THERMAL_LIMIT` auto-safe: `headroom_c` and `throttling` are what the FSM
reads.

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| `load_w` | `ComputeSubsystem.draw_w` (engine, each tick) | Junction heat dissipation, watts |
| `ambient_c` | `SensorsSubsystem.temp_c` (engine, each tick) | Exogenous ambient, degrees C |

## State (truth())

| Field | Units | Notes |
|-------|-------|-------|
| `junction_c` / `enclosure_c` | C | The two integrated states |
| `headroom_c` | C | `junction_temp_throttle - junction_c` (positive == cool) |
| `throttling` | bool | True when `junction_c >= junction_temp_throttle` |
| `junction_temp_throttle` / `junction_temp_max` | C | Profile thresholds |

## Outputs (sensor_obs())

| Field | Units | Sigma |
|-------|-------|-------|
| `junction_c` | C | 1.0 |
| `enclosure_c` | C | 0.5 |
| `ambient_c` | C | 0.5 |

## Profile fields

```yaml
thermal:
  ambient_c_default: 25
  junction_temp_max: 95
  junction_temp_throttle: 85               # throttling and headroom datum
  thermal_resistance_c_per_w: 0.30         # junction-to-enclosure R_je
  enclosure_to_ambient_resistance_c_per_w: 0.5   # enclosure-to-ambient R_ea
  enclosure_mass_kg: 1.2
  enclosure_specific_heat_j_per_kg_k: 900  # C_e = mass * specific heat
  junction_heat_capacity_j_per_k: 5.0      # C_j
  headroom_threshold_c: 5.0                # SC-2 floor
```

## Known limitations

- Two thermal nodes only. There is no spatial gradient within the junction or
  the enclosure, and no separate heat-sink or board node.
- Constant thermal resistances. `R_je` and `R_ea` are fixed; real convection
  is temperature- and orientation-dependent, and the linear assumption is
  weakest at extreme ambients (the estimator card marks sub -10 C headroom
  `confidence_low`).
- Ambient is exogenous, not modelled. It is whatever the sensor pack reports;
  enclosure-to-ambient coupling does not feed back into the room.
- A pack-borne obstruction (clothing, pack contents) that raises the real
  junction temperature is not represented; the heat sink is assumed
  unobstructed.
