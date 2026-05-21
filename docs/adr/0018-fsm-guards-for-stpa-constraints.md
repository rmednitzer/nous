# ADR 0018: FSM transition guards for STPA safety constraints

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0004, ADR 0009

## Context

The hand-rolled FSM in `src/nous/state/machine.py` admits every transition
listed in the explicit table. The STPA artefacts under `docs/stpa/`
specify several preconditions the FSM should enforce, but the v0.1 table
left those constraints to the controller. In particular, SC-2 (no
MISSION transition while thermal headroom is exhausted) and the UCAs for
`state_transition` were unenforceable in code.

A controller bug, a stale estimate, or a malicious peer could therefore
drive the simulator into MISSION on a hot device. That defeats the
purpose of recording the constraint in `docs/stpa/05-safety-constraints.md`.

## Decision

`StateMachine.transition` takes an optional `context: Mapping[str, Any]`
and consults a per-transition guard. The guard returns `(ok, reason)`;
on `ok=False` the FSM raises `GuardDenied` with structured attributes
and records the refusal in `refusals()` for audit. The guard set is
explicit in `_GUARDS` at the bottom of `machine.py` so the safety
preconditions live next to the transition table.

The engine surfaces a default safety context (thermal headroom, SoC
critical threshold) through `Engine.request_transition`, which merges
caller-supplied context with the engine-derived defaults. A controller
that calls the raw FSM keeps full control; the engine helper is for the
common case.

A guard that lacks the context it needs refuses the transition (fails
closed). Missing context is unobservable; the FSM cannot assume the
device is safe.

## Consequences

Easier: SC-2 is enforced in code, not just in prose. A guard refusal is
an observable signal -- the controller sees `(ok=False, reason=...)`
and the audit trail records the refused transition. The same guard
pattern extends to the `cool` and `recover` triggers, both of which had
their own UCAs.

Harder: a controller that does not surface a safety context cannot
transition to MISSION at all. The default-deny stance is intentional
-- a missing context is treated the same as an unsafe one -- but a
sleeping controller is a brick-walled simulator. The integration test
in `tests/integration/test_concurrent_anomalies.py` documents the
contract a controller must meet.

Alternatives rejected:

- A separate "policy" layer on top of the FSM. Splits the constraint
  across two files and lets the FSM ship with a bypass.
- Guards as decorators on the transition table. Harder to mypy; harder
  to enumerate the guarded transitions in one screen.

## Revisit triggers

- A new UCA needs a context that does not fit `Mapping[str, Any]`.
- The guard set exceeds ~15 entries and the per-transition lookup is no
  longer the cheapest abstraction.
- An external safety analyser (Polyspace, Astrée) needs to round-trip
  the guard predicates as constraints.
