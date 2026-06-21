# Model card: Power subsystem

**Module:** `src/nous/subsystems/power.py`

**Backlog:** BL-003

## Scope

A single Li-ion battery pack. State is integrated over a tick loop using
coulomb counting against an effective capacity that combines a Peukert
correction (high-current discharge) and a thermal derate (high cell
temperature). Terminal voltage is a linear open-circuit curve between
``voltage_v_min`` (0% SoC) and ``voltage_v_max`` (100% SoC), reduced by
the ohmic drop ``I * internal_resistance_ohm``.

The subsystem is *primary*: every load served by ``nous`` ultimately
draws from this pack. The APU contributes only charge, never load
(ADR-0015).

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| ``load_w`` | engine (compute + accessories; BL-007 wires the real value) | Watts, >= 0 |
| ``charge_w`` | ``ApuSubsystem.total_w`` | Bus regulator clips to ``charge_limit_w`` |
| ``cell_c`` | thermal subsystem (BL-005); defaults to ambient | Degrees C |

## State (truth())

| Field | Units | Notes |
|-------|-------|-------|
| ``soc_pct`` | % | Coulomb-counted, clamped to [0, 100] |
| ``voltage_v`` | V | Linear OCV minus ohmic drop |
| ``current_a`` | A | Net (positive on discharge, negative on charge) |
| ``remaining_wh`` | Wh | ``battery_wh * soc_pct / 100`` |
| ``endurance_min`` | min or None | None when ``load_w <= charge_w`` |
| ``flag`` | enum | ``nominal``, ``low``, ``critical``, ``empty``, ``full`` |

## Outputs (sensor_obs())

| Field | Units | Sigma |
|-------|-------|-------|
| ``soc_pct`` | % | 0.5 (calibrated bound; see estimator covariance) |
| ``voltage_v`` | V | 0.05 |
| ``current_a`` | A | 0.10 |
| ``load_w`` | W | 0.25 (well-known engine input; ADR 0083) |

## Profile fields

```yaml
power:
  battery_wh: 588               # nominal pack capacity (Wh)
  voltage_v_nominal: 14.4
  voltage_v_min: 12.0           # at 0% SoC
  voltage_v_max: 16.8           # at 100% SoC
  internal_resistance_ohm: 0.05
  rated_current_a: 5.0          # Peukert reference current
  peukert_k: 1.04
  soc_pct_low_threshold: 20     # ``flag = low`` below this
  soc_pct_critical_threshold: 5
  thermal_derate_c: 45          # capacity derate starts at this cell temperature
  thermal_derate_slope_per_c: 0.02
  charge_limit_w: 100           # bus regulator: max accepted from APU
```

## Known limitations

- Linear OCV. Real Li-ion is a piecewise curve with a flat plateau
  between roughly 20% and 80% SoC. The simulator's slope is sufficient
  to drive a voltage estimator but is not calibrated against any
  particular cell.
- One-iteration fixed point between current and terminal voltage. The
  simulator does not solve the implicit system; instead it uses the
  previous tick's current. At a 2 Hz tick the error is small.
- Single thermal node. Cell temperature is treated as uniform across
  the pack; pack-level thermal gradients are not modelled.
- Li-ion only. Other chemistries are tracked under BL-042. See
  ``LIMITATIONS.md`` L8.
