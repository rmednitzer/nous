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
    MISSION --> SAFE: safe
    MISSION --> FAULT: fault
    MISSION --> SHUTDOWN: shutdown
    RELAY --> DEGRADED: degrade
    RELAY --> IDLE: complete
    RELAY --> SAFE: safe
    RELAY --> FAULT: fault
    RELAY --> SHUTDOWN: shutdown
    MONITORING --> DEGRADED: degrade
    MONITORING --> IDLE: complete
    MONITORING --> SAFE: safe
    MONITORING --> FAULT: fault
    MONITORING --> SHUTDOWN: shutdown
    C2 --> DEGRADED: degrade
    C2 --> IDLE: complete
    C2 --> SAFE: safe
    C2 --> FAULT: fault
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
| `degrade` | `<active mode> -> DEGRADED` | controller, or the engine's auto-safing loop (ADR 0027/0028) |
| `thermal_limit` | `MISSION -> THERMAL_LIMIT` | controller, or auto-safing on an SC-2 violation |
| `low_power` | `MISSION -> LOW_POWER` | controller, or auto-safing on an SC-8 violation |
| `safe` | `<active mode> / <impaired mode> -> SAFE` | controller, or auto-safing on an incapacitated operator |
| `cool`, `recover` | recovery exits from impaired postures | controller (gated, never auto-initiated) |
| `complete` | `<active mode> -> IDLE` | controller |
| `shutdown` | `<most modes> -> SHUTDOWN` | controller |
| `reset` | `FAULT -> STOWED`, `SHUTDOWN -> STOWED` | controller |
| `fault` | `<most modes> -> FAULT` | engine or controller |

## Guards and auto-safing

Entering an operational mode is safety-gated. Every transition into
`MISSION`/`RELAY`/`MONITORING`/`C2` (and the `recover`/`cool` paths back
into them) is gated on two STPA constraints, routed through a runtime
`SafetyEnforcer` (ADR 0018/0022): SC-2 refuses when reported thermal
headroom is below the profile threshold, and SC-8 refuses when reported
state-of-charge is below the critical reserve. Gates fail closed on missing
context. `Engine.request_transition` populates the context from live
subsystem state; a refusal raises `GuardDenied`, is recorded on
`StateMachine.refusals()`, and increments the per-constraint violation
counter `device_info` surfaces.

The FSM now also initiates transitions on its own. Each tick, from an
operational mode, `Engine._auto_safe` drives the device toward a safer mode
when a constraint is violated mid-run (ADR 0027/0028): SC-8 fires
`low_power`, SC-2 fires `thermal_limit`, an incapacitated operator fires
`safe`, and a denied comms link degrades, falling back to `degrade` where a
mode lacks the precise edge. Auto-safing is one-way; recovery stays a
controller call. Every auto-safing decision is mirrored to the audit log
under `Tier.SAFETY`.

The audit log records every transition. The trigger names are stable
across versions; the schema is captured in `docs/state-machine.md`
(canonical) and in this showcase page (presentation).
