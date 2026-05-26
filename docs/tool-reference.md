# Tool reference

Generated from the FastMCP registry by
`scripts/gen_tool_reference.py`. Hand-editing this file is
discouraged: regenerate with `make tool-reference` or
`uv run python scripts/gen_tool_reference.py`. The `--check`
flag is wired into CI so a drift between source and docs fails the
build.

| Tool | Tier | Summary |
|------|------|---------|
| `anthropic_cap_status` | T0 | Surface the Anthropic daily call cap (BL-021). |
| `apu_status` | T0 | Auxiliary-power-unit state (solar, fuel cell, vehicle, USB-C PD). |
| `biometrics_status` | T0 | Operator biometrics: heart rate, core temp, hydration, cognitive load. |
| `comms_state` | T0 | Comms-stack summary (per ADR-0006). |
| `comms_status` | T0 | Comms subsystem: per-link envelope, live RSSI, loss, throughput, age. |
| `compute_status` | T0 | Compute subsystem: load fraction, electrical draw, throttling. |
| `device_health` | T0 | Engine snapshot: tick, ts_s, mode, operator/comms state. |
| `device_info` | T0 | Report nous version, profile, transport, policy mode, audit path. |
| `inference_local` | T1 | Local-path inference. |
| `inference_status` | T0 | Inference subsystem totals: calls, tokens, joules, last latency. |
| `interop_decode` | T1 | Decode a hex-encoded payload via the named adapter (BL-041 / T1). |
| `interop_encode` | T1 | Encode ``data`` via the named interop adapter (BL-041 / T1). |
| `interop_formats` | T0 | List the interop adapters the server knows about. |
| `position_status` | T0 | Position subsystem: lat/lon/alt ground truth, fix state, drift. |
| `power_status` | T0 | Battery state-of-charge, draw, projected endurance. |
| `profile_reload` | T2 | Hot-reload the hardware profile from disk. |
| `scenario_inject` | T2 | Fire a single scenario injector against the live engine. |
| `scenario_load` | T2 | Load and run a scenario YAML against the engine. |
| `self_estimator_status` | T0 | Estimator covariances, last update times, divergence flags. |
| `self_model_assess` | T0 | Self-model capability assessment with calibrated p5/p50/p95 bands. |
| `self_model_viability` | T0 | Decide whether a task is feasible against the current capabilities. |
| `sensors_status` | T0 | Environmental sensor pack: ambient temp, humidity, baro pressure. |
| `state_get` | T0 | Current FSM mode. |
| `state_history` | T0 | Recent FSM transitions (oldest first; up to ``limit`` rows). |
| `storage_status` | T0 | Storage subsystem: capacity, used, wear, write rate. |
| `thermal_status` | T0 | Two-state thermal model (junction + enclosure + ambient). |

Every tool runs through the audited runner. Output bodies are SHA-256
hashed; the audit record never contains the body itself. See
`src/nous/runner.py` and ADR-0001.

## Parameter schemas

Per-tool JSON Schema for the input shape. Generated from the FastMCP
tool registry.

### `anthropic_cap_status`

```json
{
  "properties": {},
  "title": "anthropic_cap_statusArguments",
  "type": "object"
}
```

### `apu_status`

```json
{
  "properties": {},
  "title": "apu_statusArguments",
  "type": "object"
}
```

### `biometrics_status`

```json
{
  "properties": {},
  "title": "biometrics_statusArguments",
  "type": "object"
}
```

### `comms_state`

```json
{
  "properties": {},
  "title": "comms_stateArguments",
  "type": "object"
}
```

### `comms_status`

```json
{
  "properties": {},
  "title": "comms_statusArguments",
  "type": "object"
}
```

### `compute_status`

```json
{
  "properties": {},
  "title": "compute_statusArguments",
  "type": "object"
}
```

### `device_health`

```json
{
  "properties": {},
  "title": "device_healthArguments",
  "type": "object"
}
```

### `device_info`

```json
{
  "properties": {},
  "title": "device_infoArguments",
  "type": "object"
}
```

### `inference_local`

```json
{
  "properties": {
    "max_tokens": {
      "default": 128,
      "title": "Max Tokens",
      "type": "integer"
    },
    "prompt": {
      "title": "Prompt",
      "type": "string"
    }
  },
  "required": [
    "prompt"
  ],
  "title": "inference_localArguments",
  "type": "object"
}
```

### `inference_status`

```json
{
  "properties": {},
  "title": "inference_statusArguments",
  "type": "object"
}
```

### `interop_decode`

```json
{
  "properties": {
    "adapter": {
      "title": "Adapter",
      "type": "string"
    },
    "payload_hex": {
      "title": "Payload Hex",
      "type": "string"
    }
  },
  "required": [
    "adapter",
    "payload_hex"
  ],
  "title": "interop_decodeArguments",
  "type": "object"
}
```

### `interop_encode`

```json
{
  "properties": {
    "adapter": {
      "title": "Adapter",
      "type": "string"
    },
    "data": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Data"
    }
  },
  "required": [
    "adapter"
  ],
  "title": "interop_encodeArguments",
  "type": "object"
}
```

### `interop_formats`

```json
{
  "properties": {},
  "title": "interop_formatsArguments",
  "type": "object"
}
```

### `position_status`

```json
{
  "properties": {},
  "title": "position_statusArguments",
  "type": "object"
}
```

### `power_status`

```json
{
  "properties": {},
  "title": "power_statusArguments",
  "type": "object"
}
```

### `profile_reload`

```json
{
  "properties": {
    "name": {
      "default": "",
      "title": "Name",
      "type": "string"
    }
  },
  "title": "profile_reloadArguments",
  "type": "object"
}
```

### `scenario_inject`

```json
{
  "properties": {
    "action": {
      "title": "Action",
      "type": "string"
    },
    "args": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Args"
    }
  },
  "required": [
    "action"
  ],
  "title": "scenario_injectArguments",
  "type": "object"
}
```

### `scenario_load`

```json
{
  "properties": {
    "path": {
      "title": "Path",
      "type": "string"
    }
  },
  "required": [
    "path"
  ],
  "title": "scenario_loadArguments",
  "type": "object"
}
```

### `self_estimator_status`

```json
{
  "properties": {},
  "title": "self_estimator_statusArguments",
  "type": "object"
}
```

### `self_model_assess`

```json
{
  "properties": {
    "question": {
      "default": "",
      "title": "Question",
      "type": "string"
    }
  },
  "title": "self_model_assessArguments",
  "type": "object"
}
```

### `self_model_viability`

```json
{
  "properties": {
    "endurance_min": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Endurance Min"
    },
    "inference_tok_per_s": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Inference Tok Per S"
    },
    "task": {
      "title": "Task",
      "type": "string"
    },
    "thermal_headroom_c": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Thermal Headroom C"
    }
  },
  "required": [
    "task"
  ],
  "title": "self_model_viabilityArguments",
  "type": "object"
}
```

### `sensors_status`

```json
{
  "properties": {},
  "title": "sensors_statusArguments",
  "type": "object"
}
```

### `state_get`

```json
{
  "properties": {},
  "title": "state_getArguments",
  "type": "object"
}
```

### `state_history`

```json
{
  "properties": {
    "limit": {
      "default": 16,
      "title": "Limit",
      "type": "integer"
    }
  },
  "title": "state_historyArguments",
  "type": "object"
}
```

### `storage_status`

```json
{
  "properties": {},
  "title": "storage_statusArguments",
  "type": "object"
}
```

### `thermal_status`

```json
{
  "properties": {},
  "title": "thermal_statusArguments",
  "type": "object"
}
```
