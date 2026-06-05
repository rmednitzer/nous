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

Two kinds of transition are gated on both constraints; the first unsatisfied
one names the refusal, and gates fail closed on missing or non-numeric
context. The first kind enters an operational mode (`MISSION`/`RELAY`/
`MONITORING`/`C2`) from `IDLE`. The second kind is the `recover`/`cool` exit
out of an impaired mode: it lands in the neutral `IDLE` (ADR 0029), not back
in the prior operational mode, but stays gated so a device cannot leave the
impaired posture until the hazard has cleared. The controller then re-selects
an operational mode through a first-kind gate.

| Transition | Constraint | Hazard | Mechanism |
|------------|------------|--------|-----------|
| `IDLE -mission-> MISSION` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `IDLE -relay-> RELAY` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `IDLE -monitoring-> MONITORING` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `IDLE -c2-> C2` | SC-2, SC-8 | H-2, H-8 | entry gate |
| `DEGRADED -recover-> IDLE` | SC-2, SC-8 | H-2, H-8 | impaired-exit gate |
| `THERMAL_LIMIT -cool-> IDLE` | SC-2, SC-8 | H-2, H-8 | impaired-exit gate |
| `LOW_POWER -recover-> IDLE` | SC-2, SC-8 | H-2, H-8 | impaired-exit gate |

## Auto-safing

Each tick evaluates these conditions in priority order and fires the first
that trips. The preferred trigger is taken when the mode offers it; otherwise
the condition falls back to its own fallback (per-condition, ADR 0029). The
move is one-way: recovery is a controller call that the gates re-check, and
the chosen safer mode also actuates (entering `LOW_POWER`/`THERMAL_LIMIT`/
`SAFE` caps compute load; ADR 0029). The conditions fire from an operational
mode; the operator condition (only) also fires from an impaired mode, so a
confirmed incapacitation deepens an already-impaired posture to `SAFE`.

| Priority | Condition | Source | Preferred trigger | Fallback | Addresses |
|----------|-----------|--------|-------------------|----------|-----------|
| 1 | Operator `INCAPACITATED` (debounced) | `OperatorState` label (biometrics estimate) | `safe` | `safe` | H-2, H-8 (no supervisor) |
| 2 | SC-8 power reserve violated | enforcer | `low_power` | `degrade` | H-8 |
| 3 | SC-2 thermal headroom violated | enforcer | `thermal_limit` | `degrade` | H-2 |
| 4 | Comms `DENIED` (RELAY/C2 only) | `CommsState` label (reported state) | `degrade` | `degrade` | operational prudence |

`MISSION` offers `low_power` and `thermal_limit`, so it reaches the precise
safer mode; `RELAY`/`MONITORING`/`C2` fall back to `degrade` for the enforcer
hazards (ADR 0028 records why they do not gain their own edges). The operator
condition is the exception: its fallback is also `safe` (a reachability
invariant guarantees `safe` from every operational and impaired mode), so it
never downgrades to `degrade`. Because the operator label reads the biometrics
Kalman estimate, it is debounced over a few consecutive ticks; the enforcer
and comms conditions read smoothly-evolving reported state and stay
instantaneous.

The first three conditions control numbered hazards: an incapacitated
operator means no one can supervise the device near its thermal or power
edge (H-2, H-8), and the enforcer conditions are SC-8 and SC-2 directly. The
comms-`DENIED` rule is operational prudence rather than a hazard control,
and it applies only to the link-bearing modes (`RELAY`/`C2`): a relay or a
command loop that has lost its link should not hold a full workload it can
no longer be told to stop, so it degrades to a posture the controller can
resume once a link returns. A `MISSION` or `MONITORING` run that does not
depend on comms is left alone.

## Failsafe reachability

The reachability invariants are not prose claims; `tests/unit/
test_fsm_reachability.py` walks the table and fails the build if any breaks.

The load-bearing one is that every operational or impaired mode reaches
`SAFE` in exactly one `safe` trigger, so the fail-safe posture is never more
than a step away from anywhere the device is doing work or already impaired.
The companion invariant (ADR 0030) is that the terminal `FAULT` is reachable
in exactly one `fault` trigger from every *powered* mode (`BOOT`, `IDLE`, the
operational modes, the impaired modes, and `SAFE`), because a hardware fault is
mode-independent and unrecoverable and must never be refused or stranded one
rung short of the terminal. `SHUTDOWN` is reachable from every operating or
impaired mode, and the terminal modes (`SHUTDOWN`, `FAULT`) leave only via
`reset`. None of the `safe` or `fault` failsafe edges are gated: a path to the
fail-safe or fault state must never be refused.
