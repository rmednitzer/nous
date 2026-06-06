# ADR 0032: FSM terminal-control tools

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0021, ADR 0030, ADR 0031

## Context

ADR 0031 registered `state_transition` (T2) for the reversible mission-posture
transitions and deliberately made it refuse the terminal `fault` and `shutdown`
triggers, pointing the controller at "the irreversible `state_force_*` tool".
Those tool names were classified T3 in `policy.py` under the ADR 0007
forward-classification rule, but they were never registered, so the refusal
message was a dangling reference: a controller told to use `state_force_fault`
or `state_force_shutdown` found no such tool. The FSM therefore had no registered
path to FAULT (the hardware-fault posture ADR 0030 makes reachable in one step
from every powered mode) or to SHUTDOWN.

## Decision

Register `state_force_fault` and `state_force_shutdown` (T3) in
`src/nous/tools/state.py`. Each is a no-argument tool that fires its fixed FSM
trigger through `Engine.request_transition` and returns `{ok, mode, reason}`.
The trigger is fixed by the tool name rather than a free-form argument, so the
tool cannot be steered to a non-terminal transition; the reversible transitions
stay with `state_transition`. FAULT and SHUTDOWN are terminal (reset-only),
which is why they earn the irreversible tier: under `guarded` or `readonly`
policy they are refused unless explicitly allowed, while `state_transition` (T2)
is admitted. Recovery out of a terminal posture is a separate, deliberate act
through the T2 tool (`reset` to STOWED, then `boot`), since STOWED is not
terminal. No FSM change and no new policy tier: both names were already in
`_IRREVERSIBLE_TOOLS` and the engine seam already exists. The tool surface grows
from thirty-one to thirty-three.

This ADR also disposes of the rest of the forward-classified-but-unregistered
tier so the gap is closed by decision, not left implicit:

- `request_transition` (was T2): retired. `state_transition` is the registered
  tool and `request_transition` is the engine method it wraps, not a second
  tool. The redundant classification is removed; `classify` still returns
  STATEFUL for any unknown name via the additive-surface rule, so the change is
  behaviour-preserving.
- `db_reset` and `audit_rotate` (T3): kept classified but deliberately
  unregistered. They are operator and sysadmin maintenance actions (wipe the
  SQLite store, force-rotate the audit log), not device-control actions for an
  LLM controller; putting destructive infrastructure operations on the model's
  tool surface is out of scope. The classification stays so an operator-only
  surface, if one is ever added, inherits the right tier.
- The remaining names (`scenario_status` / `scenario_pause` / `scenario_resume`
  / `scenario_reset`, `tick_advance`, `comms_send` / `comms_publish`,
  `inference_cloud` / `inference_request`, `self_model_publish`) need new engine
  seams or design (a stateful scenario runner, a concurrency-safe manual tick, a
  cloud-inference path with cap accounting) and stay tracked in the backlog.

## Consequences

The `state_transition` refusal message now resolves to real tools, and the FSM's
terminal postures are reachable through the audited tool surface for the first
time. The control surface is symmetric and complete: T2 for the reversible
transitions and recovery, T3 for the two terminal transitions. Because the force
tools are T3, a guarded-mode deployment that allowlists only `state_transition`
still cannot fault or shut down the device; an operator opts into that authority
explicitly. Every call is audited like any other, and the FSM guard and refusal
records are unchanged.

Alternatives rejected:

- **A single `state_force(trigger)` tool.** Two named, no-argument tools read
  better in the audit log and let a policy allow-regex target one terminal
  action without the other. A free-form trigger argument would also reopen the
  path to the non-terminal transitions the T2 tool already owns.
- **Calling `Engine.stop()` from `state_force_shutdown`.** `stop()` is the
  process-lifecycle teardown (it clears the `_started` flag). The controller's
  shutdown is the modelled SHUTDOWN posture, not a halt of the simulator
  process. Keeping the tool a pure FSM driver matches `state_force_fault`, which
  has no lifecycle counterpart.
- **Registering `db_reset` / `audit_rotate`.** Operator actions, not controller
  actions (see above).

## Revisit triggers

- An operator-only (non-controller) administrative surface is added, at which
  point `db_reset` / `audit_rotate` move onto it.
- The FSM gains another terminal mode, which would get its own force tool.
