# 10 -- FSM constraints mapping

This artefact traces every safety-relevant state-machine transition back to
the constraint it enforces and the hazard that constraint addresses. It is
the mechanical join a conformity reviewer needs: pull a transition, find its
constraint and hazard here, and cross-check the enforcing code and the
`Tier.SAFETY` audit records. The transitions and triggers are defined in
`src/nous/state/machine.py`; the gate evaluators and the auto-safing loop
live in `src/nous/safety/enforcer.py` and `src/nous/engine.py`.

The state machine protects the operational modes two ways. An **entry gate**
refuses a controller-requested transition *into* an operational mode when a
constraint is violated (ADR 0018, ADR 0022). **Auto-safing** moves the FSM
*out of* an operational mode on a tick when a constraint is violated mid-run
(ADR 0027, ADR 0028). Both route through the same enforcer, and both are
mirrored to the audit log under `Tier.SAFETY`.

## Entry gates

Every transition into an operational mode (`MISSION`/`RELAY`/`MONITORING`/
`C2`) is gated on both constraints; the first unsatisfied one names the
refusal. Gates fail closed on missing context.

| Transition | Constraint | Hazard | Mechanism |
|------------|------------|--------|-----------|
| `IDLE -mission-> MISSION` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `IDLE -relay-> RELAY` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `IDLE -monitoring-> MONITORING` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `IDLE -c2-> C2` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `DEGRADED -recover-> MISSION` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `THERMAL_LIMIT -cool-> MISSION` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `LOW_POWER -recover-> MISSION` | SC-2, SC-8 | H-2, H-8 | entry gate |

## Auto-safing

From an operational mode, each tick evaluates these conditions in priority
order and fires the first that trips. The preferred trigger is taken when
the mode offers it; otherwise the condition falls back to `degrade`. The
move is one-way: recovery is a controller call that the entry gates re-check.

| Priority | Condition | Source | Preferred trigger | Fallback | Addresses |
|----------|-----------|--------|-------------------|----------|-----------|
| 1 | Operator `INCAPACITATED` | `OperatorState` label | `safe` | `degrade` | H-2, H-8 (no supervisor) |
| 2 | SC-8 power reserve violated | enforcer | `low_power` | `degrade` | H-8 |
| 3 | SC-2 thermal headroom violated | enforcer | `thermal_limit` | `degrade` | H-2 |
| 4 | Comms `DENIED` | `CommsState` label | `degrade` | `degrade` | operational prudence |

`MISSION` offers `low_power` and `thermal_limit`, so it reaches the precise
safer mode; `RELAY`/`MONITORING`/`C2` fall back to `degrade` (ADR 0028
records why they do not gain their own edges).

The first three conditions control numbered hazards: an incapacitated
operator means no one can supervise the device near its thermal or power
edge (H-2, H-8), and the enforcer conditions are SC-8 and SC-2 directly. The
comms-`DENIED` rule is operational prudence rather than a hazard control: a
device that has lost its command channel should not hold a full operational
workload it can no longer be told to stop, so it degrades to a posture the
controller can resume once a link returns.

## Failsafe reachability

The reachability invariants are not prose claims; `tests/unit/
test_fsm_reachability.py` walks the table and fails the build if any breaks.

The load-bearing one is that every operational or impaired mode reaches
`SAFE` in exactly one `safe` trigger, so the fail-safe posture is never more
than a step away from anywhere the device is doing work or already impaired.
`SHUTDOWN` is reachable from every operating or impaired mode, every
operational mode can `fault`, and the terminal modes (`SHUTDOWN`, `FAULT`)
leave only via `reset`. None of the `safe` or `fault` edges are gated: a
path to the fail-safe state must never be refused.
