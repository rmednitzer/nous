# State machine

The simulator's mission posture is a hand-rolled FSM over thirteen
modes. The transition table lives in `src/nous/state/machine.py`; this
page is the canonical reference.

## Modes

| Mode | Meaning |
|------|---------|
| `stowed` | Powered off; in the pack. |
| `boot` | Boot sequence in progress. |
| `idle` | Powered, no active mission. |
| `mission` | Active mission load (compute + comms + sensors). |
| `relay` | Acting as a relay node (comms focus). |
| `monitoring` | Environmental monitoring only. |
| `c2` | Command and control loop. |
| `degraded` | At least one subsystem outside its envelope. |
| `thermal_limit` | Thermal headroom exhausted; load throttled. |
| `low_power` | Battery SoC below threshold; non-essential off. |
| `safe` | Operator-driven safe posture. |
| `shutdown` | Cooperative shutdown in progress. |
| `fault` | Unrecoverable fault. |

## Triggers

A trigger is a string that names a transition. The allowed
`(mode, trigger)` pairs are explicit; an unknown pair raises a
`ValueError` so silent no-ops are impossible.

```mermaid
stateDiagram-v2
    [*] --> stowed
    stowed --> boot: boot
    boot --> idle: ready
    boot --> fault: fault
    idle --> mission: mission
    idle --> relay: relay
    idle --> monitoring: monitoring
    idle --> c2: c2
    idle --> shutdown: shutdown
    mission --> degraded: degrade
    mission --> thermal_limit: thermal_limit
    mission --> low_power: low_power
    mission --> idle: complete
    mission --> fault: fault
    degraded --> mission: recover
    degraded --> safe: safe
    degraded --> fault: fault
    thermal_limit --> mission: cool
    thermal_limit --> safe: safe
    low_power --> mission: recover
    low_power --> safe: safe
    safe --> idle: recover
    safe --> shutdown: shutdown
    fault --> stowed: reset
    shutdown --> stowed: reset
```

## Safety gates

Entering an operational mode is safety-gated. `_SAFETY_GATES` in
`src/nous/state/machine.py` maps each transition into `mission`, `relay`,
`monitoring`, or `c2` (and the `recover`/`cool` paths back into them) to two
STPA constraints: SC-2 floors thermal headroom at the profile threshold, and
SC-8 floors state-of-charge at the profile's critical reserve. Both fail
closed when the context is missing, so a sleeping controller cannot brick its
way into an operational mode.

The machine routes every gate through a `SafetyEnforcer` (ADR 0022). A
refused gate raises `GuardDenied` carrying the enforcer's structured reason,
the refusal is recorded on `StateMachine.refusals()`, and the enforcer
increments a per-constraint violation counter that `device_info` surfaces
under `safety`. `Engine.request_transition` fills the safety context from
live subsystem state and mirrors each check to the audit log under
`Tier.SAFETY`, so an after-action review can pull every safety event by tier
and group it by `constraint_id`.

## Auto-safing

The safety gates refuse an unsafe transition the controller *requests*;
ADR 0027 adds the other half, a control law the engine runs on itself.
On each tick, from an operational mode (`mission`, `relay`, `monitoring`,
`c2`), `Engine._auto_safe` asks the same enforcer whether the live
reported state still satisfies SC-8 (power reserve) then SC-2 (thermal
headroom). The first violated constraint fires one transition toward
safety: the mode's preferred safer trigger when the table offers one
(`low_power` for SC-8, `thermal_limit` for SC-2, both from `mission`),
otherwise `degrade`.

Auto-safing is one-way. The engine only ever moves toward a safer mode and
never auto-recovers; `recover` and `cool` stay controller calls that the
enforcer re-checks. That one-way property is the hysteresis: with no
auto-recovery there is no oscillation to damp, so the loop needs no
debounce. Each auto-safing decision is recorded to `state_history` with an
`auto-safe:` reason and mirrored to the audit log under `Tier.SAFETY`
(tool `auto_safe`).

The label-driven conditions (comms `DENIED`, operator `INCAPACITATED`)
and the per-mode `thermal_limit`/`low_power` edges that would let
`relay`/`monitoring`/`c2` reach the precise safer mode land with the
reachability work, alongside direct `safe` from every operational mode.

## Vocabularies

`OperatorState` and `CommsState` are derived from estimator state. ADR
0027 begins consuming them for auto-safing, but the label-driven
transitions land with the reachability edges; today the labels are still
primarily summary fields the controller reads (see ADR-0006).
