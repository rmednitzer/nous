# Model card: Environmental sensor subsystem

**Module:** `src/nous/subsystems/sensors.py`

**Backlog:** BL-009

## Scope

Carries ambient temperature, relative humidity, and barometric pressure as
ground truth, with the profile's advertised noise envelope. This subsystem is
the **authoritative ambient source**: the engine reads `temp_c` each tick to
drive the thermal subsystem's ambient input, so a single `set_temp_c` call
("the patrol crossed the snow line") propagates through enclosure cooling,
battery cell temperature, and the FSM thermal-headroom guard.

The values are held exogenous ground truth, not a dynamic model: `step()` only
advances the clock. The environmental physics (a room warming, a front moving
through) is expressed by the controller or a scenario setting the values, not
by internal evolution.

## Inputs

| Seam | Notes |
|------|-------|
| `set_temp_c` | Any finite scalar |
| `set_humidity_pct` | Clamped to [0, 100] |
| `set_baro_kpa` | Clamped to [10, 200] kPa, so a wild injection cannot poison consumers |

## State (truth())

| Field | Units | Notes |
|-------|-------|-------|
| `temp_c` | C | Authoritative ambient for the thermal model |
| `humidity_pct` | % | Clamped [0, 100] |
| `baro_kpa` | kPa | Clamped [10, 200] |

## Outputs (sensor_obs())

| Field | Units | Sigma |
|-------|-------|-------|
| `temp_c` | C | 0.2 (profile `temp_c_sigma`) |
| `humidity_pct` | % | 1.0 (profile `humidity_pct_sigma`) |
| `baro_kpa` | kPa | 0.1 (profile `baro_kpa_sigma`) |

## Profile fields

```yaml
sensors:
  environmental:
    temp_c_default: 22          # falls back to thermal.ambient_c_default
    humidity_pct_default: 50
    baro_kpa_default: 101.3
    temp_c_sigma: 0.2
    humidity_pct_sigma: 1.0
    baro_kpa_sigma: 0.1
```

## Known limitations

- No environmental dynamics. The values are held until set; there is no
  diurnal cycle, no humidity/temperature coupling, no pressure-altitude
  relationship modelled in the subsystem (the estimator filters noise but does
  not add physics).
- The three channels are independent ground truth; a physically inconsistent
  triple (for example a high temperature with saturated humidity at low
  pressure) is accepted as set.
- Pressure and humidity drive no downstream physics today; only `temp_c` is
  consumed (by the thermal model). They exist for interop and situational
  reporting.
