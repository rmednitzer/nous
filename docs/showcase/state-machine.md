# State machine

The mission posture FSM is hand rolled (ADR 0004). The transition
table lives in `src/nous/state/machine.py` and is reviewable in one
screen. The diagram below mirrors that table; if they drift, the
diagram is wrong, not the code.

Badge: `filtered`. The FSM does not estimate, but its transitions are
audited and its refusal of unknown triggers is a hard error rather
than a silent no-op.

```mermaid
stateDiagram-v2
    [*] --> STOWED
    STOWED --> BOOT: boot
    BOOT --> IDLE: ready
    BOOT --> FAULT: fault
    BOOT --> SHUTDOWN: shutdown
    IDLE --> MISSION: mission
    IDLE --> RELAY: relay
    IDLE --> MONITORING: monitoring
    IDLE --> C2: c2
    IDLE --> SHUTDOWN: shutdown
    MISSION --> DEGRADED: degrade
    MISSION --> THERMAL_LIMIT: thermal_limit
    MISSION --> LOW_POWER: low_power
    MISSION --> IDLE: complete
    MISSION --> FAULT: fault
    MISSION --> SHUTDOWN: shutdown
    RELAY --> DEGRADED: degrade
    RELAY --> IDLE: complete
    RELAY --> SHUTDOWN: shutdown
    MONITORING --> DEGRADED: degrade
    MONITORING --> IDLE: complete
    MONITORING --> SHUTDOWN: shutdown
    C2 --> DEGRADED: degrade
    C2 --> IDLE: complete
    C2 --> SHUTDOWN: shutdown
    DEGRADED --> MISSION: recover
    DEGRADED --> SAFE: safe
    DEGRADED --> FAULT: fault
    DEGRADED --> SHUTDOWN: shutdown
    THERMAL_LIMIT --> MISSION: cool
    THERMAL_LIMIT --> SAFE: safe
    THERMAL_LIMIT --> SHUTDOWN: shutdown
    LOW_POWER --> MISSION: recover
    LOW_POWER --> SAFE: safe
    LOW_POWER --> SHUTDOWN: shutdown
    SAFE --> IDLE: recover
    SAFE --> SHUTDOWN: shutdown
    FAULT --> STOWED: reset
    SHUTDOWN --> STOWED: reset
```

## Trigger surface

| Trigger | Effect | Originator (today) |
| --- | --- | --- |
| `boot` | `STOWED -> BOOT` | controller |
| `ready` | `BOOT -> IDLE` | controller |
| `mission`, `relay`, `monitoring`, `c2` | `IDLE -> <mode>` | controller |
| `degrade` | `<active mode> -> DEGRADED` | controller or, when wired, the state machine itself (BL-022) |
| `thermal_limit` | `MISSION -> THERMAL_LIMIT` | controller (DR-2 will let the FSM raise this itself when the thermal estimator lands) |
| `low_power` | `MISSION -> LOW_POWER` | controller (DR-2, again) |
| `cool`, `recover`, `safe` | exits from degraded postures | controller |
| `complete` | `<active mode> -> IDLE` | controller |
| `shutdown` | `<most modes> -> SHUTDOWN` | controller |
| `reset` | `FAULT -> STOWED`, `SHUTDOWN -> STOWED` | controller |
| `fault` | `<most modes> -> FAULT` | engine or controller |

## Guards and what it does not do today

The FSM refuses unsafe transitions when the controller provides the
relevant safety context. ADR 0018 wires two guards:

- `IDLE -> MISSION`, `DEGRADED -> recover`, `THERMAL_LIMIT -> cool`
  refuse when `thermal_headroom_c < thermal_headroom_threshold_c`
  (SC-2 from the STPA artefacts).
- `LOW_POWER -> recover` refuses when `soc_pct < soc_pct_critical`.

`Engine.request_transition` populates the safety context from live
subsystem state, so a controller calling the FSM through the engine
sees the guards in action. A guard refusal raises `GuardDenied` and
is recorded on `StateMachine.refusals()` for the audit log.

The FSM still does not *initiate* transitions on its own (it raises
`thermal_limit` and `low_power` only when a controller or the engine
asks it to). DR-2 tracks that follow-up under BL-022.

The audit log records every transition. The trigger names are stable
across versions; the schema is captured in `docs/state-machine.md`
(canonical) and in this showcase page (presentation).
