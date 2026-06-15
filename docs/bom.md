# Bill of Materials

Every numeric value in `profiles/*.yaml` must trace back to a row in this
file. This is the authoritative reference: a new component lands here
first, then in a profile YAML. When a profile drifts from a row below,
either the YAML is wrong or the BOM is out of date; in either case the
realism rule (`AGENTS.md`) is violated.

Source citations name the vendor and the product. Datasheet URLs are
omitted intentionally: vendor PDF locations move, but vendor + product
name is searchable and stable.

## Conventions

| Column | Meaning |
|--------|---------|
| Part | Vendor product name or standard designation |
| Vendor / body | Manufacturer or standards body |
| Reference | Datasheet, MIL standard, or published spec that fixes the numbers |
| Profile usage | Which YAML field(s) and which profile(s) |
| Notes | Divergence from the reference or rationale for the chosen number |

## Batteries

| Part | Vendor | Reference | Profile usage | Notes |
|------|--------|-----------|---------------|-------|
| BB-2590/U | Bren-Tronics | MIL-PRF-32383/3 ; Bren-Tronics BB-2590/U datasheet | `power.battery_wh: 294` (jetson-orin-nx) ; 2x for `power.battery_wh: 588` (jetson-agx-orin) | 14.4 V nominal, ~1.4 kg, Li-ion. 294 Wh is the 9.9 Ah (BT-70791CG class) variant; 2x gives the 588 Wh AGX pack. Internal resistance 50-80 mOhm typical for a 4S pack of this rating. |
| Spot battery | Boston Dynamics | Boston Dynamics Spot product specification | `power.battery_wh: 605`, `voltage_v_nominal: 41.6` (spot-core) | ~4.2 kg Li-ion. Published figures vary by revision: current vendor listings show ~564 Wh and a 35-58.8 V range (no nominal stated). The profile keeps the earlier 605 Wh / 41.6 V spec; Spot is a demonstration profile, so the figure stays pending a single authoritative source (AUDIT-2026-06-15b). |
| 3S 2P 18650 pack | Generic COTS | Samsung INR18650-25R datasheet (representative cell) | `power.battery_wh: 55`, `voltage_v_nominal: 11.1` (pi5-hailo) | 6x 18650 cells, ~9.25 Wh per cell at 2500 mAh and 3.7 V nominal -> ~55 Wh pack. |

## Compute modules

| Part | Vendor | Reference | Profile usage | Notes |
|------|--------|-----------|---------------|-------|
| Jetson AGX Orin 64GB | NVIDIA | Jetson AGX Orin Series Data Sheet | `compute.draw_w_idle: 8`, `compute.draw_w_load: 60` (jetson-agx-orin) | Power envelope 15-60 W selectable via `NV_POWER_MODE`. Idle figure assumes MAXN with light load. |
| Jetson Orin NX 16GB | NVIDIA | Jetson Orin NX Series Data Sheet | `compute.draw_w_idle: 5`, `compute.draw_w_load: 25` (jetson-orin-nx) | Power envelope 10-25 W. |
| Raspberry Pi 5 (8GB) | Raspberry Pi Ltd | Raspberry Pi 5 product brief | Part of `compute.draw_w_idle: 3`, `compute.draw_w_load: 12` (pi5-hailo) | 3-8 W typical CPU; package includes Hailo accelerator (next row). |
| Hailo-8L M.2 | Hailo | Hailo-8L AI Acceleration Module datasheet | Part of pi5-hailo `compute.draw_w_load` envelope | 13 TOPS; ~1.5 W typical, up to ~6.6 W for the M.2 module. |
| Spot CORE I/O payload | Boston Dynamics | Boston Dynamics Spot CORE I/O documentation | `compute.draw_w_idle: 30`, `compute.draw_w_load: 90` (spot-core) | x86-class payload computer; envelope from CORE I/O power budget. |

## Solar PV panels

| Part | Vendor | Reference | Profile usage | Notes |
|------|--------|-----------|---------------|-------|
| SOL90 | PowerFilm Solar | PowerFilm SOL90 datasheet | `apu.solar.panel_w_peak: 60` (jetson-agx-orin) | 90 W rollable; profile uses 60 W as a conservative real-world trim (cabling, angle, soiling). |
| MFC-40 class | Bren-Tronics | Bren-Tronics MFC product line | `apu.solar.panel_w_peak: 40` (jetson-orin-nx) | 40 W folding solar mat. |
| F15-300N | PowerFilm Solar | PowerFilm F15 series datasheet | `apu.solar.panel_w_peak: 20` (pi5-hailo) | ~20 W foldable amorphous thin-film. |

## MPPT and panel-temperature derate

| Quantity | Value | Reference |
|----------|-------|-----------|
| MPPT efficiency | 0.92 | Typical commercial MPPT controllers, 92-98% range. Conservative end picked. |
| Panel temperature coefficient | 0.4 %/C above 25 C | Typical crystalline-Si and amorphous panels: 0.3-0.5 %/C. |

## Methanol fuel cells

| Part | Vendor | Reference | Profile usage | Notes |
|------|--------|-----------|---------------|-------|
| EFOY Pro 800 class | SFC Energy | SFC EFOY Pro 800 datasheet | `apu.fuel_cell.continuous_w: 25`, `efficiency: 0.25`, `wh_per_g_fuel: 1.4` (jetson-agx-orin) | ~45 W nameplate (25 W minimum output); profile uses 25 W as a typical sustained draw. Consumption 0.9 L/kWh. |
| EFOY 80 class | SFC Energy | SFC EFOY 80 datasheet | `apu.fuel_cell.continuous_w: 15`, `efficiency: 0.25`, `wh_per_g_fuel: 1.4` (jetson-orin-nx) | Same consumption rate; smaller continuous output. |

## Methanol cartridges and energy properties

| Quantity | Value | Reference |
|----------|-------|-----------|
| Methanol density (liquid, 20 C) | 0.79 g/ml | CRC Handbook of Chemistry and Physics |
| Methanol LHV (lower heating value) | 19.9 MJ/kg = 5.53 Wh/g | NIST Chemistry WebBook |
| SFC EFOY consumption | 0.9 L/kWh ; ~711 g/kWh ; ~1.4 Wh/g electrical | SFC EFOY datasheet family |
| SFC EFOY system efficiency | ~25 % (post-BOP) | Derived: 1.4 Wh/g / 5.53 Wh/g = 0.253 |
| Cartridge sizes in use | 1 L (790 g) for jetson-agx-orin ; 0.5 L (395 g) for jetson-orin-nx | SFC M5 / M10 cartridge family |

## Vehicle / charging-tether bus

| Spec | Standards body | Reference | Profile usage | Notes |
|------|----------------|-----------|---------------|-------|
| 28 V DC ground-vehicle bus | US DoD | MIL-STD-1275 | `apu.vehicle.bus_voltage_v: 28.0`, `current_limit_a: 5.0` (jetson-agx-orin, jetson-orin-nx) | Standard 28 V DC military ground-vehicle electrical interface. (STANAG 4074 is the separate jump-start connector standard, not the bus voltage; corrected AUDIT-2026-06-15b.) 5 A current limit is a conservative accessory-port draw (140 W). |
| 12 V automotive accessory | SAE | SAE J1113 (radiated and conducted EM compatibility); ISO 16750 (general 12 V envelope) | `apu.vehicle.bus_voltage_v: 12.0`, `current_limit_a: 2.0` (pi5-hailo) | Cigarette-lighter / accessory-port class draw (24 W). |
| 48 V Spot dock | Boston Dynamics | Spot charger and dock specification | `apu.vehicle.bus_voltage_v: 48.0`, `current_limit_a: 8.0` (spot-core) | Spot's native charge bus. The "vehicle" abstraction is a stretch for a robot platform; treat as the dock-tether equivalent. |

## USB-C Power Delivery profiles

| Profile | V x A | Reference | Notes |
|---------|-------|-----------|-------|
| 15 W | 5 V x 3 A | USB-IF USB Power Delivery Specification 3.1 (SPR) | Mandatory Standard Power Range profile |
| 27 W | 9 V x 3 A | USB-IF USB PD 3.1 (SPR) | |
| 45 W | 15 V x 3 A | USB-IF USB PD 3.1 (SPR) | |
| 60 W | 20 V x 3 A | USB-IF USB PD 3.1 (SPR) | 3 A USB-C cable |
| 100 W | 20 V x 5 A | USB-IF USB PD 3.1 (SPR / EPR boundary) | 5 A USB-C cable |
| 240 W | 48 V x 5 A | USB-IF USB PD 3.1 (Extended Power Range) | EPR-capable cable |

## Thermal

| Quantity | Value | Reference | Profile usage |
|----------|-------|-----------|---------------|
| Jetson AGX Orin junction temp limit | 105 C (Tj,max) | NVIDIA Jetson AGX Orin datasheet | `thermal.junction_temp_max: 95` (jetson-agx-orin) is a deliberately conservative operating bound below Tj,max. |
| Li-ion charge derate onset | ~40-45 C cell | Generic Li-ion cell datasheets (Samsung, LG, Panasonic) | `power.thermal_derate_c: 45` (all profiles) |
| Li-ion charge derate slope | ~2 % per C above onset | Same | `power.thermal_derate_slope_per_c: 0.02` |

## Out of scope (referenced in architecture, not yet modeled)

The PMU / PDU subsystem (BL-005b) will own bus regulation, source
arbitration, CC/CV charge profile, and dual-slot hot-swap. Today the
flat `charge_limit_w` clamp lives on `PowerSubsystem`; that logic
moves onto the PMU when BL-005b lands and ADR-0015 is superseded.

Other deferred items:

- DC-DC conversion losses between APU and battery: assumed lossless.
- Per-cell thermal sensors: a single bulk cell temperature is used.
- Hand-crank generator: explicitly excluded (see
  `docs/model-cards/subsystem-apu.md`).
- Inference performance benchmarks (`compute.inference_local.*`):
  the placeholders in profile YAMLs will not survive a real
  MLPerf / llama.cpp / Hailo benchmark sweep. Tracked by BL-007
  (compute subsystem) and BL-043 (real local inference).
