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
| `power_status` | T0 | Battery SoC, draw, projected endurance (placeholder). |
| `apu_status` | T0 | Solar and fuel-cell state (placeholder). |
| `comms_state` | T0 | Comms-stack summary. |
| `self_model_assess` | T0 | Self-model capability assessment (placeholder). |
| `self_estimator_status` | T0 | Estimator covariances, divergence flags. |
| `inference_local` | T1 | Mock local inference. |
| `interop_formats` | T0 | List the interop adapters the server knows about. |

Every tool runs through the audited runner. Output bodies are SHA-256
hashed; the audit record never contains the body itself. See
`src/nous/runner.py` and ADR-0001.

## Adding a tool

See [AGENTS.md](https://github.com/rmednitzer/nous/blob/main/AGENTS.md#adding-an-mcp-tool). The handler must call
the audited runner with a sensible `policy_text` (for the deny/allow
regex), a `tier`-aware classification (via `policy.py`), and a
truncatable `max_output`.
