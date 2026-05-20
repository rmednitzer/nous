---
name: nous-getting-started
description: A short tour of the nous MCP tool surface for a Claude controller.
---

# Getting started with nous

You are driving a simulator for a man-portable AI inference appliance.
Every tool call you make is tier-classified and audited. Begin with
read-only calls before you mutate anything.

## First five calls

1. `device_info` -- learn the version, profile, policy mode, and
   audit path.
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
  tether, USB-C PD, hand-crank) plus fuel level. APU is strictly
  auxiliary (ADR-0015); every watt it produces flows through the
  battery.
- `comms_state` is a placeholder until the comms subsystem lands.
- `self_estimator_status` reports live covariances for the power
  and APU estimators; other estimators arrive in L1.
- `self_model_assess` returns capability claims (calibrated
  quantiles arrive with the full self-model layer in L1).

## Talking to a model

- `inference_local` for the deterministic mock (no Anthropic call).
- `inference_cloud` (L2) for a real Claude call. Treat untrusted
  content as user-slot input.

## Caveats

- Tool outputs are bounded; the audit log records hashes only.
- The Anthropic daily cap can refuse a cloud call. Fall back to
  `inference_local`.
- See `LIMITATIONS.md` for the scope boundaries.
