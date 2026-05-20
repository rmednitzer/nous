# ADR 0004: Hand-rolled finite-state machine

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

The simulator's mission posture is a small finite-state machine
(thirteen states in v0.1). Two off-the-shelf libraries cover this space:
`transitions` (declarative, dynamic) and `automat` (declarative,
introspectable). Both pull in dependencies and indirection that obscure
what is a one-screen problem.

## Decision

`src/nous/state/machine.py` defines `Mode` as a `StrEnum` and the
allowed transitions as an explicit
`dict[tuple[Mode, str], Mode]`. `StateMachine.transition(trigger)`
looks up the next state or raises a `ValueError` for unknown triggers.
Transition history is captured for the `state_history` tool.

## Consequences

Easier: the transition table is the spec. Adding a transition is one
dict entry plus a test. The FSM is fully covered by a single unit test
that drives every entry in the table.

Harder: there is no built-in hierarchical or parallel state support.
When that becomes necessary, the table grows quickly.

Alternatives rejected:

- `transitions` and `automat` as stated above. Both are fine libraries,
  but the cost of bringing them in (review, version pinning, mypy
  shims) is larger than the cost of hand-rolling thirteen states.

## Revisit triggers

- The mode count crosses ~50.
- A subsystem needs its own FSM with synchronised parent transitions.
- We need to externalise the FSM (e.g. to a UML model importer).
