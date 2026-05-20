# Model card: APU subsystem

**Module:** `src/nous/subsystems/apu.py`

**Backlog:** BL-005a

**Builds on:** ADR-0015 (APU strictly auxiliary)

## Scope

Five auxiliary power sources composed into a single ``total_w`` offered
to the primary battery each tick. Every source is additive; none ever
delivers power directly to compute. The bus regulator on
``PowerSubsystem.set_charge_w`` clamps the offered total to
``charge_limit_w``.

## Sources

### Solar PV with MPPT

Inputs: irradiance presented to the panel (``set_solar_insolation_w``)
or a direct override (``set_solar_w``), and panel temperature.

Output:
``min(panel_w_peak, mppt_efficiency * insolation_w * temp_derate)``
where ``temp_derate = max(0, 1 - panel_temp_derate_per_c_above_25 *
max(0, panel_temp_c - 25))``.

### Methanol fuel cell

Inputs: load fraction in [0, 1] (``set_fuelcell_load_pct``) or a direct
override (``set_fuelcell_w``).

State: ``fuel_g`` depletes at
``output_w * dt / wh_per_g_fuel``. When the tank empties, output is
forced to zero regardless of the load fraction.

Output: ``min(continuous_w, override_w or load_pct * continuous_w)``.

### Vehicle tether

Inputs: ``connected`` flag and the bus's ``offered_w``
(``set_vehicle``). When connected, output is
``min(offered_w, bus_voltage_v * current_limit_a)``.

### USB-C PD-in

Inputs: ``connected`` flag and a requested profile in W
(``set_usb_c_pd``). The negotiated output is the largest available
profile that is less than or equal to the request; if the request is
below the smallest available profile, the smallest is used.

### Hand-crank

Input: human input power (``set_hand_crank_w``). Output is
``min(input_w, max_w) * efficiency``.

## Total

```
total_w = solar_w + fuelcell_w + vehicle_w + usbc_w + hand_crank_w
```

The engine calls ``power.set_charge_w(apu.total_w)`` each tick; the
power subsystem reports ``charge_offered_w`` and ``charge_accepted_w``
separately so the controller can see how much APU power was clipped.

## Profile fields

```yaml
apu:
  solar:
    panel_w_peak: 60
    mppt_efficiency: 0.92
    panel_temp_derate_per_c_above_25: 0.004
  fuel_cell:
    continuous_w: 25
    fuel_capacity_g: 250
    efficiency: 0.45
    wh_per_g_fuel: 2.5            # electrical Wh per gram (post-cell losses)
  vehicle:
    bus_voltage_v: 28.0
    current_limit_a: 5.0
  usb_c_pd:
    profiles_w: [15, 27, 45, 60, 100]
    default_profile_w: 60
  hand_crank:
    max_w: 20
    efficiency: 0.65
```

The legacy flat fields ``solar_w_peak``, ``fuelcell_w_continuous``,
``fuelcell_fuel_capacity_g``, and ``fuelcell_efficiency`` are still
parsed when the nested form is absent, so older profiles keep working.

## Known limitations

- No source ever delivers AC power direct to compute. See ADR-0015.
- The MPPT model is a single efficiency multiplier, not an actual
  perturb-and-observe loop. A real MPPT controller hunts; the
  simulator pretends it has already found the maximum.
- Fuel cell startup transient is not modelled. Output appears
  immediately when ``load_pct`` rises above zero and disappears
  immediately when fuel runs out.
- Vehicle tether contact resistance is not modelled. ``offered_w``
  is assumed to arrive at the bus voltage minus zero drop.
- USB-C PD negotiation is discrete (a single profile selection per
  ``set_usb_c_pd`` call). The simulator does not model the PD
  message exchange itself.
