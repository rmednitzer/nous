# Changelog

All notable changes to `nous` land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Profile values anchored to real spec sheets. Each profile YAML
  now carries a citation header naming the battery, compute,
  solar, fuel cell, and vehicle bus references:
  Bren-Tronics BB-2590/U (296 Wh, 14.4 V) for the Jetson
  profiles, Boston Dynamics Spot battery (605 Wh, 41.6 V) for
  spot-core, SFC EFOY (~0.9 L/kWh, ~25% system efficiency, ~1.4
  Wh/g electrical) for the methanol fuel cells,
  PowerFilm SOL90 / Bren-Tronics MFC class for the solar panels,
  NATO STANAG 4074 for the vehicle tether. ``AGENTS.md`` now
  states the realism rule explicitly so future profile edits
  stay grounded.

- Primary battery model: Li-ion with Peukert correction and thermal
  derate. Subsystem integrates coulomb counting over an effective
  capacity that scales with current and cell temperature; bus
  regulator clips APU-offered charge to ``charge_limit_w`` and
  reports ``charge_offered_w`` vs ``charge_accepted_w``. 1-D Kalman
  filter over (SoC, voltage) with covariance bounds documented in
  the model card. Tracked by `BL-003`.

- APU subsystem expanded to four auxiliary sources: solar PV with
  MPPT, methanol fuel cell, vehicle tether, and USB-C PD-in. Each
  source has scenario-friendly setters
  (``set_solar_insolation_w``, ``set_fuelcell_load_pct``,
  ``set_vehicle``, ``set_usb_c_pd``) plus direct overrides for
  compatibility with the existing ``inject_apu`` scenario action.
  Fuel cell tracks methanol mass and stops at empty;
  ``wh_per_g_fuel`` is derived from ``efficiency * 5.53 Wh/g``
  (methanol LHV) when not explicitly set. The USB-C
  ``default_profile_w`` is run through the PD negotiation at
  construction time. Per-source 1-D Kalman estimator. Tracked by
  `BL-005a`.

- Engine ``tick()`` now wires power and APU through the loop:
  ``apu.step`` -> ``power.set_charge_w(apu.total_w)`` ->
  ``power.step`` -> estimator updates. The compute-driven load and
  thermal cell temperature fall back to profile defaults until the
  compute (`BL-007`) and thermal (`BL-005`) subsystems land.

- MCP tools ``power_status``, ``apu_status``, and
  ``self_estimator_status`` now return real engine values instead
  of placeholder stubs.

- ADR-0015: APU is strictly auxiliary; the primary battery is the
  sole power bus. Compute never draws from an APU source directly.

- New model cards: ``subsystem-power``, ``subsystem-apu``,
  ``estimator-apu``.

- Hardware profile schema extended with the new
  ``power.{voltage_v_min,voltage_v_max,internal_resistance_ohm,
  rated_current_a,thermal_derate_slope_per_c,charge_limit_w}``
  fields and the nested ``apu.{solar,fuel_cell,vehicle,usb_c_pd,
  hand_crank}`` blocks. The legacy flat ``apu`` keys are still
  parsed for backward compatibility.

- Self-updating deployment posture: `nous-auto-update.timer` polls
  `origin/main` every 5 minutes and fast-forwards + reinstalls +
  restarts when HEAD advances. New script `deploy/auto-update.sh`
  and systemd units under `deploy/systemd/`. Disable with
  `systemctl disable --now nous-auto-update.timer`.

- OAuth 2.1 authorization-server provider (file-backed DCR + PKCE +
  rotating refresh, single-client lockdown) wired into the FastMCP HTTP
  transport. Caddy carveout for `/authorize` and `/.well-known/oauth-*`;
  set `NOUS_OAUTH_ENABLED=true` and `NOUS_OAUTH_ISSUER=https://...` to
  enable. Tracked by `BL-019`.
- v0.1 scaffold: project layout, governance docs, audited MCP tool
  surface, finite-state machine, tick-loop engine, hardware-profile
  loader, OAuth issuer shape, and typed stubs for subsystems, estimators,
  the self-model, and interop adapters. Tracked by `BL-001`.
