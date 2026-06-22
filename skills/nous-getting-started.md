---
name: nous-getting-started
description: A short tour of the nous MCP tool surface for a Claude controller.
---

# Getting started with nous

You are driving a simulation-based digital twin of an edge-AI inference
appliance, exposed over MCP. Every tool call you make is
tier-classified and audited. Begin with read-only calls before you mutate
anything.

## First five calls

1. `device_info` -- learn the version, profile, policy mode, audit
   path, and the safety posture (per-constraint violation counts).
2. `device_health` -- a snapshot of the engine: tick, simulated
   timestamp, FSM mode.
3. `state_get` -- the current FSM mode.
4. `state_history` -- the recent transition history.
5. `interop_formats` -- the adapters the server knows about.

## Reading the simulator

- `power_status` returns the live Li-ion pack state (SoC, terminal
  voltage, current, accepted vs offered APU charge, endurance
  estimate, low/critical flag).
- `apu_status` returns per-source power (solar, fuel cell, vehicle
  tether, USB-C PD) plus fuel level. APU is strictly auxiliary
  (ADR-0015); every watt it produces flows through the battery.
- `thermal_status` returns the two-state thermal model (junction +
  enclosure + ambient) and the throttle headroom.
- `compute_status` returns the load fraction, electrical draw, and
  throttle and saturation flags; this is the authoritative load
  source the power and thermal subsystems read each tick.
- `storage_status` returns capacity, used / free space, NAND wear,
  and write rate.
- `comms_state` and `comms_status` return the aggregate FSM signal
  plus the per-link envelopes (live RSSI, loss, throughput, age).
- `comms_outbox` returns the store-and-forward queue: depth, queued
  bytes, the per-precedence and per-link breakdown, the head package,
  and the disposition counters (BL-077 / ADR 0047).
- `position_status` returns lat / lon / alt, fix state, dead-reckoning
  duration, and the position Kalman estimate.
- `imu_status` returns the strapdown accelerometer + yaw-rate gyro
  truth, the true sensor biases and noise envelope, and the GNSS/INS
  EKF's inferred biases with one-sigma bounds (BL-026 / ADR 0084).
- `sensors_status` returns ambient temperature, humidity, and
  barometric pressure with Kalman covariance.
- `biometrics_status` returns heart rate, core temperature, hydration,
  and cognitive-load proxy with Kalman covariance.
- `inference_status` returns running totals (local calls, tokens,
  joules, last latency) and the profile's nominal capacity.
- `self_estimator_status` reports live covariances for every
  estimator that has landed.
- `self_model_assess` returns one claim per capability, each with a
  `point`, calibrated `p5`/`p50`/`p95` quantiles, a `confidence`, and the
  `drivers`. Read the `p5` band and `confidence` for viability and safety
  decisions; do not treat a wide band as if it were the point estimate.

## Driving the device

Reads are safe; control tools mutate state and audit at a higher tier. A
freshly started engine settles in the `IDLE` standby posture (ADR 0039).

- `state_transition` (T2) drives the mission posture: from `IDLE`,
  `mission` / `relay` / `monitoring` / `c2`, or the recoverable
  `safe` hold. Operational entries are SC-2 / SC-8 gated and refuse when
  thermal headroom or power reserve is short.
- `state_force_fault` / `state_force_shutdown` (T3, irreversible) drive the
  device into the reset-only FAULT / SHUTDOWN postures. Recovery is a
  deliberate sequence on the `state_transition` path: `reset` then `boot`
  (back to `BOOT`, from which `ready` reaches `IDLE`).
- `comms_send` / `comms_publish` (T2) account a transmission on a link;
  `self_model_publish` (T2) pushes the situation or assess read through an
  interop adapter onto a link (ADR 0041).
- `comms_enqueue` / `comms_flush` (T2) drive the store-and-forward outbox:
  queue a package while a link is degraded or denied, and force a
  triage-ordered drain when it recovers (BL-077 / ADR 0047).
- `scenario_load` / `scenario_inject` / `profile_reload` (T2) drive scenarios
  and reconfiguration. A `scenario_load` with `mode="session"` runs the
  timeline as a stateful session controlled by `scenario_status` /
  `scenario_pause` / `scenario_resume` / `scenario_reset`, and
  `tick_advance` (T1) fast-forwards simulated time (see the scenario
  walkthrough).

## Deployment posture

The live VM tracks `origin/main`; the development line may be ahead
of `main` and therefore ahead of the live MCP. If the read surface
above is not all reachable, the live host is on an older
revision (see [`docs/audit-2026-06-06.md`](../docs/audit-2026-06-06.md)
§6 for the most recent live-MCP probe).

## Talking to a model

- `inference_local` for the deterministic mock (no Anthropic call).
- `inference_cloud` for the cloud path: it prefers the capped Anthropic
  client and degrades to the local mock when the cap is exhausted, comms are
  down, or the call fails, so you always get an answer (ADR 0034). The
  response reports `path` (`cloud` or `local_mock`) and a cap snapshot.
- `anthropic_cap_status` reports whether a cloud call would be admitted
  (key configured and cap not exhausted).

## Caveats

- Tool outputs are bounded; the audit log records hashes only.
- The FSM can auto-safe on a tick: from an operational mode, a violated
  safety constraint (thermal SC-2, power SC-8) or an incapacitated operator
  drives the device toward a safer mode on its own, mirrored to the audit
  log under `Tier.SAFETY`. Watch `state_get` and `device_info.safety`.
- `anthropic_cap_status` shows `exhausted` when the daily cap is reached;
  `inference_local` is the fallback.
- See `LIMITATIONS.md` for the scope boundaries.
