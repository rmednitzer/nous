# Architecture

`nous` is a simulation-based digital twin of an edge-AI inference appliance,
built around a tick-driven engine that orchestrates subsystem physics,
estimator updates, and self-model claims. A FastMCP server sits on top,
exposing the engine to a controller. The deployment
target is a single VM.

## Layers

1. **Engine** (`src/nous/engine.py`). Holds subsystems, estimators, and
   the self-model. `tick()` advances every subsystem by `dt`, feeds
   each estimator its observation, and refreshes the self-model.
2. **Subsystems** (`src/nous/subsystems/`). Each subsystem implements
   the `Subsystem` Protocol (`step / truth / sensor_obs`). Curves and
   limits come from the hardware profile.
3. **Estimators** (`src/nous/estimators/`). Each estimator implements
   the `Estimator` Protocol (`predict / update / state`). The
   simplest filter that meets the model card's covariance bound is the
   right choice.
4. **Self-model** (`src/nous/self_model/`). Aggregates estimator state
   into capability claims (`endurance`, `thermal_headroom`,
   `inference_capacity`) with calibrated quantiles.
5. **State machine** (`src/nous/state/`). Explicit-table FSM over the
   mission posture; vocabularies for `OperatorState` and `CommsState`.
6. **Server** (`src/nous/server.py`). FastMCP server. Every tool call
   runs through the audited runner.
7. **Runner + policy + audit** (`src/nous/{runner,policy,audit}.py`).
   Tier classification, admission, JSONL audit (output hashed only).
8. **Interop adapters** (`src/nous/interop/`). CoT, SensorThings, MISB
   KLV, NMEA 0183, STANAG 4774/4778, MQTT.
9. **OAuth issuer** (`src/nous/auth/`). File-backed; single-client by
   default.

## Data flow

A tick:

```
profile -> Subsystem.step(dt) -> Subsystem.sensor_obs() -> Estimator.update()
Estimator.predict(dt) -> Estimate -> SelfModel.assess() -> Capability claims
```

A tool call:

```
Controller -> FastMCP -> runner.run(...)
  classify -> admit/refuse
  execute work coroutine
  truncate output
  AuditLogger.write(record)
return body
```

## External surfaces

- **MCP tools** -- the thirty-tool surface is documented in
  [tool-reference.md](tool-reference.md). It carries the full L1 read
  surface (one read tool per subsystem plus estimator summary) plus the
  mutating tools `scenario_load` / `scenario_inject` / `profile_reload`
  (T2) and `audit_resync` (T2). A few names stay classified-but-unwired
  in `policy.py` (e.g. `comms_send`, `state_transition`, `inference_cloud`)
  pending their subsystems.
- **OAuth issuer** -- file-backed, single-client by default. The
  Caddyfile template gates `/authorize` and `/.well-known/oauth-*` on
  the operator's CIDR plus the Anthropic ranges.
- **Audit JSONL** -- append-only at `$NOUS_HOME/audit.jsonl`. Output
  bodies are SHA-256 hashed, never written.
- **Interop adapters** -- documented in `docs/conformance/`.

## Boundaries

What `nous` is not:

- Not a real device. Outputs that look like operational telemetry
  (CoT, MQTT, MISB KLV) are *simulated*.
- Not a learned self-model. The self-model is parametric and reviewable.
- Not a multi-operator system. The v0.1 simulation is single-operator.
- Not a mesh / DTN stack. Comms are point-to-point.

See [LIMITATIONS.md](https://github.com/rmednitzer/nous/blob/main/LIMITATIONS.md) for the full list.

## Where to extend

- A new subsystem: add a module under `src/nous/subsystems/`, wire it
  into `Engine.__init__`, ship a model card under
  `docs/model-cards/`. See [AGENTS.md](https://github.com/rmednitzer/nous/blob/main/AGENTS.md#canonical-recipes).
- A new estimator: pair it with the subsystem and add a model card.
- A new MCP tool: register it in the relevant `src/nous/tools/` module
  (ADR 0021), classify it in `policy.py`, regenerate `tool-reference.md`
  with `make schema`.
- A new adapter: implement the `Adapter` Protocol, document its
  conformance posture under `docs/conformance/`.
