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
- `position_status` returns lat / lon / alt, fix state, dead-reckoning
  duration, and the position EKF estimate.
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

## Deployment posture

The live VM tracks `origin/main`; the development line may be ahead
of `main` and therefore ahead of the live MCP. If the read surface
above is not all reachable, the live host is on an older
revision (see [`docs/audit-2026-05-23.md`](../docs/audit-2026-05-23.md)
§4 for the most recent live-MCP probe).

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
