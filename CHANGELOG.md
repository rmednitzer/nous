# Changelog

All notable changes to `nous` land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Deployment baseline moves to Ubuntu 26.04 LTS / Python 3.14 (ADR
  0016). `deploy/install.sh` selects `python3.14` -> `python3.13` ->
  `python3` so the bundle still works on 24.04 hosts. ADR 0008 is
  superseded.

### Added

- Hardening on `deploy/systemd/nous.service`: `ProtectClock`,
  `ProtectHostname`, `ProtectProc=invisible`, `ProcSubset=pid`,
  `RestrictNamespaces`, `RestrictAddressFamilies=AF_UNIX AF_INET
  AF_INET6`, `MemoryDenyWriteExecute`, `RemoveIPC`,
  `KeyringMode=private`, `UMask=0077`, empty
  `CapabilityBoundingSet`/`AmbientCapabilities`, and a
  `SystemCallFilter=@system-service` allowlist with the privileged
  groups (`@privileged @resources @debug @mount @cpu-emulation
  @obsolete @raw-io @reboot @swap`) explicitly denied. Lifted by the
  systemd version Ubuntu 26.04 ships.

### Fixed

- `tests/unit/test_anthropic_client.py` lands as the dedicated
  spine test for `src/nous/anthropic_client.py` (AUDIT.md C1 + H1
  partial, ADR-0005, BL-021). Cap exhaustion, UTC rollover,
  corrupted-state fail-closed, and concurrent multiprocess locking
  via `multiprocessing.Barrier` are all covered. The concurrency
  test pins C1 closed: it fails deterministically against the
  legacy unlock-before-flush ordering and passes deterministically
  against the patched flush-then-fsync-then-unlock ordering.
  `tests/unit/test_call_cap.py` is consolidated into the new file.

- `deploy/systemd/nous.service` now lists `/var/log/nous` in
  `ReadWritePaths=` so the audit log can be written when
  `NOUS_AUDIT_PATH=/var/log/nous/audit.jsonl` (the path the
  cloud-init env file and `deploy/logrotate.conf` already target).
  Previously only `/var/lib/nous` was writable under
  `ProtectSystem=strict`, so the audit sink degraded to stderr on a
  fresh install.

- ``docs/bom.md`` (Bill of Materials) added as the authoritative
  cross-reference for every numeric value in ``profiles/*.yaml``.
  One row per modeled component (battery, compute, solar, fuel
  cell, fuel cartridge, vehicle bus, USB-C PD profile, thermal
  envelope) naming the vendor / product / reference document and
  the profile fields it drives. New numbers land in the BOM
  first, then in a profile. ``AGENTS.md`` and
  ``docs/hardware-profiles.md`` link the BOM as the realism
  source of truth.

- ``BL-005b`` added to the backlog: PMU/PDU subsystem covering
  bus regulation, source arbitration, CC/CV charge profile, and
  dual-slot battery hot-swap. Lifts ``charge_limit_w`` and the
  offered/accepted clamp off ``PowerSubsystem`` onto a new
  ``PmuSubsystem``; supersedes ADR-0015. Dual-slot model:
  primary + secondary battery, PMU arbitrates the active source,
  the inactive slot can be removed without bus collapse.

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
  fields and the nested ``apu.{solar,fuel_cell,vehicle,usb_c_pd}``
  blocks. The legacy flat ``apu`` keys are still parsed for
  backward compatibility.

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
