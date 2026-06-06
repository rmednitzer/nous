# ADR 0039: Engine start completes to the IDLE standby posture

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** rmednitzer
- **Builds on:** ADR 0004 (hand-rolled FSM), ADR 0024 (process-scoped engine lifecycle), ADR 0031 (state_transition control tool)

## Context

`Engine.start()` drove the FSM `STOWED -> BOOT` and stopped there. `BOOT` is
defined as "boot sequence in progress" (`docs/state-machine.md`), a transient
bring-up state, while `IDLE` is "powered, no active mission", the standby
posture every recovery path (`recover` / `cool` / `complete`) lands in and the
one the gated operational entries start from. The `ready` edge (`BOOT -> IDLE`)
was modelled as a controller action, and nous has no on-board platform-manager
that would issue it: the controller is external (the Claude session, STPA
artefact 06). So an unattended deployment (`nous-prod-01`, which has no attached
controller) booted and then sat in the transient `BOOT` state indefinitely.
BL-066 / ADR 0031 observed this (`mode=boot` at tick 937) and gave the
controller a registered path onward by registering `state_transition`, but left
`start()` parking in `BOOT`.

Resting in "boot in progress" is a semantic mismatch: completing the boot
sequence is deterministic plant behaviour, not a supervisory decision. The
`ready` edge is also the one bring-up transition that is **ungated**: unlike the
operational entries it carries no SC-2 (thermal) or SC-8 (power) check, so
firing it on start cannot violate a safety constraint.

## Decision

`Engine.start()` now drives `STOWED -> BOOT -> IDLE`: after firing `boot` it
fires the ungated `ready` edge, so a started engine settles in `IDLE`. Both
transitions are recorded to the state-transition log, so the bring-up sequence
stays visible in `state_history`.

The line between plant behaviour and supervision is preserved. Completing boot
to `IDLE` is the plant powering up; the genuinely supervisory choices, the gated
`IDLE -> mission / relay / monitoring / c2` entries, stay controller-driven and
SC-2 / SC-8 gated, and the terminal `fault` / `shutdown` triggers stay on their
own tools. The FSM transition table is unchanged; only `start()` does more. The
scenario runner drops its own post-start `ready` step, which `start()` now
subsumes.

No new mode is introduced. `IDLE` already is the powered-idle / standby /
ready-for-tasking posture; a distinct `STANDBY` or `READY` mode would add FSM
surface for a state the model already has.

## Consequences

An unattended deployment now rests in `IDLE` (a sensible, observable standby)
instead of a transient `BOOT`, which is what an operator expects from a
platform-management controller completing power-on. `device_health` on the live
VM reads `idle` after each auto-update restart rather than `boot`. The
self-model situation summary reads `nominal` from a healthy idle device rather
than `standby`.

The originator of `boot` and `ready` is now the engine's own bring-up (still
controller-issuable through `state_transition` when the FSM is in the matching
mode); `docs/showcase/state-machine.md` and `docs/state-machine.md` record the
shift. The change touches `engine.py` and the scenario runner, not the
high-blast-radius `state/machine.py`. Tests that asserted `mode == boot`
immediately after `start()` / `build_app` are updated to expect `idle`, and a
new test pins that `start()` lands in `IDLE` and logs `boot` then `ready`.

## Revisit triggers

Revisit if a deliberate pre-ready hold becomes meaningful, for example a
power-on self-test that must pass before the device declares itself ready: that
would reintroduce an explicit `ready` step (controller- or self-test-gated) or a
distinct `STANDBY` mode, and `start()` would stop at `BOOT` again. Revisit if a
deployment needs to boot directly into an operational mode without an external
controller, which would mean an on-board mission manager the twin deliberately
does not model today.
