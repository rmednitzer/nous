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
   `inference_capacity`, `perception_range`) with calibrated quantiles.
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

- **MCP tools** -- the fifty-plus-tool surface is documented in
  [tool-reference.md](tool-reference.md). It carries the full L1 read
  surface (a read tool for each subsystem, with comms exposing
  `comms_state`, `comms_status`, and the store-and-forward `comms_outbox`,
  plus the `dtn_mesh` and `emcon_status` reads, an estimator summary, and the
  `scenario_status` session read) plus the
  mutating tools `scenario_load` / `scenario_inject` / `profile_reload`,
  `comms_send` / `comms_publish` / `comms_enqueue` / `comms_flush` / `dtn_send`,
  `self_model_publish`, `emcon_set`, `state_transition`,
  `inference_cloud`,
  and `audit_resync` (all T2), the reversible session and stepping controls
  `scenario_pause` / `scenario_resume` / `scenario_reset` / `tick_advance`
  (T1, ADR 0040), and the terminal `state_force_fault` /
  `state_force_shutdown` at T3. The names still classified-but-unregistered
  in `policy.py` are so by design (`inference_request` as the redundant twin
  of `inference_cloud`, and the operator-only `db_reset` / `audit_rotate`),
  forward-classified per ADR 0007 with dispositions recorded in ADR 0033.
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
- Not a real radio network. The comms links and the DTN mesh overlay
  (multi-node store-and-forward with custody transfer, BL-056) are
  simulated over abstract peer nodes, not physical radios.

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
