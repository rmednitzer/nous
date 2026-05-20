# Hardware profiles

A hardware profile YAML describes one physical device. Curves and
limits in the profile drive the subsystem physics; code reads the
profile, never the other way round (ADR-0003).

## Reference profile

`profiles/jetson-agx-orin.yaml` is the canonical Jetson AGX Orin 64GB
reference. Battery capacity, Peukert exponent, thermal limits, compute
power across load fractions, sensor noise stddevs, and comms link
envelopes live there.

## Other profiles

| Profile | Notes |
|---------|-------|
| `jetson-orin-nx.yaml` | Smaller compute module, smaller battery. |
| `pi5-hailo.yaml` | Raspberry Pi 5 with a Hailo-8L accelerator. |
| `spot-core.yaml` | Boston Dynamics Spot's compute core. |

## Schema

```yaml
schema_version: "0.1.0"
name: jetson-agx-orin
description: ...

power:
  battery_wh: 588
  voltage_v_nominal: 14.4
  voltage_v_min: 12.0
  voltage_v_max: 16.8
  internal_resistance_ohm: 0.05
  rated_current_a: 5.0
  peukert_k: 1.04
  soc_pct_low_threshold: 20
  soc_pct_critical_threshold: 5
  thermal_derate_c: 45
  thermal_derate_slope_per_c: 0.02
  charge_limit_w: 100

apu:
  solar:
    panel_w_peak: 60
    mppt_efficiency: 0.92
    panel_temp_derate_per_c_above_25: 0.004
  fuel_cell:
    continuous_w: 25
    fuel_capacity_g: 250
    efficiency: 0.45
    wh_per_g_fuel: 2.5
  vehicle:
    bus_voltage_v: 28.0
    current_limit_a: 5.0
  usb_c_pd:
    profiles_w: [15, 27, 45, 60, 100]
    default_profile_w: 60
  hand_crank:
    max_w: 20
    efficiency: 0.65

thermal:
  ambient_c_default: 25
  junction_temp_max: 95
  thermal_resistance_c_per_w: 0.3

compute:
  draw_w_idle: 8
  draw_w_load: 60
  load_curve:
    - { load_pct: 0, draw_w: 8 }
    - { load_pct: 50, draw_w: 35 }
    - { load_pct: 100, draw_w: 60 }

sensors:
  position:
    lat_sigma: 3.0e-5
    lon_sigma: 3.0e-5
    alt_m_sigma: 5
  ...

comms:
  links:
    - id: lte
      bandwidth_bps: 20_000_000
      rssi_dbm_nominal: -75
      loss_pct_nominal: 0.5
```

The APU section also accepts the legacy flat fields ``solar_w_peak``,
``fuelcell_w_continuous``, ``fuelcell_fuel_capacity_g``, and
``fuelcell_efficiency`` for backward compatibility; the nested form is
preferred for new profiles.

L1 ships a Pydantic schema model (`src/nous/profiles/schema.py`) and a
JSON Schema artefact under `docs/schema/`. The `make schema` target
regenerates both.
