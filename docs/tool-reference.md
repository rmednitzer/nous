# Tool reference

Generated from the FastMCP registry by
`scripts/gen_tool_reference.py`. Hand-editing this file is
discouraged: regenerate with `make schema` or
`uv run python scripts/gen_tool_reference.py`. The docs site
regenerates this file at build time; run `make schema` to refresh
the committed copy after changing a tool's signature or docstring.

| Tool | Tier | Summary |
|------|------|---------|
| `anthropic_cap_status` | T0 | Surface the Anthropic daily call cap (BL-021). |
| `apu_status` | T0 | Auxiliary-power-unit state (solar, fuel cell, vehicle, USB-C PD). |
| `audit_anchor_verify` | T0 | Cross-check the daily audit anchors against the chain (BL-031, ADR 0026). |
| `audit_resync` | T2 | Re-open the audit sink in place (closes AUDIT-2026-05-23 N2). |
| `audit_summary` | T0 | Read-only view of the audit handler's state. |
| `audit_verify` | T0 | Verify the audit hash chain on disk (BL-016, ADR 0025). |
| `biometrics_status` | T0 | Operator biometrics: heart rate, core temp, hydration, cognitive load. |
| `comms_enqueue` | T2 | Queue a package for store-and-forward when comms are degraded (T2, BL-077). |
| `comms_flush` | T2 | Force a triage-ordered drain of the outbox against the live links (T2, BL-077). |
| `comms_outbox` | T0 | Read the store-and-forward outbox: depth, triage breakdown, counters (T0, BL-077). |
| `comms_publish` | T2 | Encode ``data`` via an interop adapter and transmit it on a link (T2, ADR 0033). |
| `comms_send` | T2 | Record a transmission of ``n_bytes`` on link ``link_id`` (T2, ADR 0033). |
| `comms_state` | T0 | Comms-stack summary (per ADR-0006). |
| `comms_status` | T0 | Comms subsystem: per-link envelope, RSSI, loss, throughput, age, age-out count/time. |
| `compute_status` | T0 | Compute subsystem: load fraction, electrical draw, throttling. |
| `device_health` | T0 | Engine snapshot: tick, ts_s, mode, operator/comms state. |
| `device_info` | T0 | Report version, profile, transport, policy, audit/anchor, persistence, safety posture. |
| `dtn_mesh` | T0 | Read the DTN mesh: nodes, contacts, in-transit bundles, counters (T0, BL-056). |
| `dtn_send` | T2 | Originate a bundle at the device node toward a remote EID (T2, BL-056). |
| `emcon_set` | T2 | Set the active EMCON emission profile (T2, BL-060 / ADR 0065). |
| `emcon_status` | T0 | Read the EMCON emission posture: active profile and permitted links (T0, BL-060). |
| `inference_cloud` | T2 | Cloud-path inference through the SC-5 fallback ladder (ADR 0034). |
| `inference_local` | T1 | Local-path inference. |
| `inference_status` | T0 | Inference subsystem totals: calls, tokens, joules, last latency. |
| `interop_decode` | T1 | Decode a hex-encoded payload via the named adapter (BL-041 / T1). |
| `interop_encode` | T1 | Encode ``data`` via the named interop adapter (BL-041 / T1). |
| `interop_formats` | T0 | List the interop adapters the server knows about. |
| `position_status` | T0 | Position subsystem: lat/lon/alt ground truth, fix state, drift. |
| `power_status` | T0 | Battery state-of-charge, draw, projected endurance. |
| `profile_reload` | T2 | Hot-reload the hardware profile from disk. |
| `scenario_inject` | T2 | Fire a single scenario injector against the live engine. |
| `scenario_load` | T2 | Load a scenario YAML and execute it against the engine (T2). |
| `scenario_pause` | T1 | Freeze the scenario session's clock (T1, reversible; ADR 0040). |
| `scenario_reset` | T1 | Detach and clear the scenario session (T1; ADR 0040). |
| `scenario_resume` | T1 | Unfreeze a paused scenario session (T1, reversible; ADR 0040). |
| `scenario_status` | T0 | Progress of the stateful scenario session, if any (T0, ADR 0040). |
| `self_estimator_status` | T0 | Estimator means, covariances, and per-filter health. |
| `self_model_assess` | T0 | Self-model capability assessment with calibrated p5/p50/p95 bands. |
| `self_model_publish` | T2 | Publish the current self-model read over a comms link (T2, ADR 0041). |
| `self_model_situation` | T0 | Fused situational read: capabilities, provenance, posture, safety, recommendations. |
| `self_model_viability` | T0 | Decide whether a task is feasible against the current capabilities. |
| `sensors_status` | T0 | Environmental sensor pack: ambient temp, humidity, baro pressure. |
| `state_force_fault` | T3 | Force the device into the terminal FAULT posture (T3, ADR 0032). |
| `state_force_shutdown` | T3 | Force the device into the terminal SHUTDOWN posture (T3, ADR 0032). |
| `state_get` | T0 | Current FSM mode plus the labels a controller queries together. |
| `state_history` | T0 | Recent FSM transitions (oldest first; up to ``limit`` rows). |
| `state_transition` | T2 | Drive the mission-posture FSM through one explicit trigger (ADR 0031). |
| `storage_status` | T0 | Storage subsystem: capacity, used, wear, write rate. |
| `thermal_status` | T0 | Two-state thermal model (junction + enclosure + ambient). |
| `tick_advance` | T1 | Advance simulated time by ``n`` engine ticks, synchronously (T1). |

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

### `audit_anchor_verify`

```json
{
  "properties": {},
  "title": "audit_anchor_verifyArguments",
  "type": "object"
}
```

### `audit_resync`

```json
{
  "properties": {},
  "title": "audit_resyncArguments",
  "type": "object"
}
```

### `audit_summary`

```json
{
  "properties": {},
  "title": "audit_summaryArguments",
  "type": "object"
}
```

### `audit_verify`

```json
{
  "properties": {},
  "title": "audit_verifyArguments",
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

### `comms_enqueue`

```json
{
  "properties": {
    "bundle_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Bundle Id"
    },
    "dest_eid": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Dest Eid"
    },
    "kind": {
      "default": "raw",
      "title": "Kind",
      "type": "string"
    },
    "link_id": {
      "title": "Link Id",
      "type": "string"
    },
    "n_bytes": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "N Bytes"
    },
    "payload_hex": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Payload Hex"
    },
    "precedence": {
      "default": "routine",
      "title": "Precedence",
      "type": "string"
    },
    "ttl_s": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Ttl S"
    }
  },
  "required": [
    "link_id"
  ],
  "title": "comms_enqueueArguments",
  "type": "object"
}
```

### `comms_flush`

```json
{
  "properties": {
    "link_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Link Id"
    },
    "max_bytes": {
      "anyOf": [
        {
          "type": "integer"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Max Bytes"
    }
  },
  "title": "comms_flushArguments",
  "type": "object"
}
```

### `comms_outbox`

```json
{
  "properties": {},
  "title": "comms_outboxArguments",
  "type": "object"
}
```

### `comms_publish`

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
    },
    "link_id": {
      "title": "Link Id",
      "type": "string"
    }
  },
  "required": [
    "link_id",
    "adapter"
  ],
  "title": "comms_publishArguments",
  "type": "object"
}
```

### `comms_send`

```json
{
  "properties": {
    "link_id": {
      "title": "Link Id",
      "type": "string"
    },
    "n_bytes": {
      "title": "N Bytes",
      "type": "integer"
    }
  },
  "required": [
    "link_id",
    "n_bytes"
  ],
  "title": "comms_sendArguments",
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

### `dtn_mesh`

```json
{
  "properties": {},
  "title": "dtn_meshArguments",
  "type": "object"
}
```

### `dtn_send`

```json
{
  "properties": {
    "bundle_id": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Bundle Id"
    },
    "custody": {
      "default": false,
      "title": "Custody",
      "type": "boolean"
    },
    "dest_eid": {
      "title": "Dest Eid",
      "type": "string"
    },
    "lifetime_s": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Lifetime S"
    },
    "n_bytes": {
      "default": 1024,
      "title": "N Bytes",
      "type": "integer"
    },
    "precedence": {
      "default": "routine",
      "title": "Precedence",
      "type": "string"
    }
  },
  "required": [
    "dest_eid"
  ],
  "title": "dtn_sendArguments",
  "type": "object"
}
```

### `emcon_set`

```json
{
  "properties": {
    "profile": {
      "title": "Profile",
      "type": "string"
    }
  },
  "required": [
    "profile"
  ],
  "title": "emcon_setArguments",
  "type": "object"
}
```

### `emcon_status`

```json
{
  "properties": {},
  "title": "emcon_statusArguments",
  "type": "object"
}
```

### `inference_cloud`

```json
{
  "properties": {
    "max_tokens": {
      "default": 512,
      "title": "Max Tokens",
      "type": "integer"
    },
    "prompt": {
      "title": "Prompt",
      "type": "string"
    },
    "tier": {
      "default": "default",
      "title": "Tier",
      "type": "string"
    }
  },
  "required": [
    "prompt"
  ],
  "title": "inference_cloudArguments",
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
    "mode": {
      "default": "run",
      "title": "Mode",
      "type": "string"
    },
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

### `scenario_pause`

```json
{
  "properties": {},
  "title": "scenario_pauseArguments",
  "type": "object"
}
```

### `scenario_reset`

```json
{
  "properties": {},
  "title": "scenario_resetArguments",
  "type": "object"
}
```

### `scenario_resume`

```json
{
  "properties": {},
  "title": "scenario_resumeArguments",
  "type": "object"
}
```

### `scenario_status`

```json
{
  "properties": {},
  "title": "scenario_statusArguments",
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

### `self_model_publish`

```json
{
  "properties": {
    "adapter": {
      "default": "mqtt",
      "title": "Adapter",
      "type": "string"
    },
    "kind": {
      "default": "situation",
      "title": "Kind",
      "type": "string"
    },
    "link_id": {
      "title": "Link Id",
      "type": "string"
    }
  },
  "required": [
    "link_id"
  ],
  "title": "self_model_publishArguments",
  "type": "object"
}
```

### `self_model_situation`

```json
{
  "properties": {},
  "title": "self_model_situationArguments",
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

### `state_force_fault`

```json
{
  "properties": {},
  "title": "state_force_faultArguments",
  "type": "object"
}
```

### `state_force_shutdown`

```json
{
  "properties": {},
  "title": "state_force_shutdownArguments",
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

### `state_transition`

```json
{
  "properties": {
    "trigger": {
      "title": "Trigger",
      "type": "string"
    }
  },
  "required": [
    "trigger"
  ],
  "title": "state_transitionArguments",
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

### `tick_advance`

```json
{
  "properties": {
    "n": {
      "default": 1,
      "title": "N",
      "type": "integer"
    }
  },
  "title": "tick_advanceArguments",
  "type": "object"
}
```
