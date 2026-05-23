# Tool reference (v0.1)

The v0.1 server advertises a representative set of tools. The full
subsystem coverage lands in L1 (see [backlog.md](backlog.md)).

> This page is hand-edited for v0.1. `scripts/gen_tool_reference.py`
> will regenerate it from the FastMCP server in L1.

| Tool | Tier | Effect |
|------|------|--------|
| `device_info` | T0 | Version, profile, transport, policy mode, audit path. |
| `device_health` | T0 | Engine snapshot: tick, ts_s, mode, operator/comms state. |
| `state_get` | T0 | Current FSM mode. |
| `state_history` | T0 | Recent FSM transitions. |
| `power_status` | T0 | Live Li-ion pack: SoC, terminal voltage, current, accepted vs offered APU charge, endurance, low/critical flag. |
| `apu_status` | T0 | Per-source APU power (solar, fuel cell, vehicle, USB-C PD) plus fuel level. |
| `thermal_status` | T0 | Two-state thermal model: junction and enclosure temperature, ambient, throttle headroom, throttling flag. |
| `compute_status` | T0 | Compute load fraction, electrical draw, throttling and saturation flags, profile-reported token capacity. |
| `inference_status` | T0 | Inference totals: local calls, tokens generated, joules consumed, last latency, profile capacity. |
| `storage_status` | T0 | Storage capacity, used / free space, NAND wear, write rate, capacity / wear flags, estimator covariance. |
| `comms_state` | T0 | Comms-stack summary (stub until BL-012). |
| `self_model_assess` | T0 | Self-model capability assessment (stub until BL-018). |
| `self_estimator_status` | T0 | Estimator covariances (live for power, APU, thermal, and compute; other estimators land in L1). |
| `inference_local` | T1 | Local-path inference. Returns synthetic response plus latency, energy joules, and the profile's nominal token rate. |
| `interop_formats` | T0 | List the interop adapters the server knows about. |

Every tool runs through the audited runner. Output bodies are SHA-256
hashed; the audit record never contains the body itself. See
`src/nous/runner.py` and ADR-0001.

## Adding a tool

See [AGENTS.md](https://github.com/rmednitzer/nous/blob/main/AGENTS.md#adding-an-mcp-tool). The handler must call
the audited runner with a sensible `policy_text` (for the deny/allow
regex), a `tier`-aware classification (via `policy.py`), and a
truncatable `max_output`.
