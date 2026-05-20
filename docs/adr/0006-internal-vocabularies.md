# ADR 0006: Internal vocabularies for OperatorState and CommsState

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

The self-model layer needs to summarise the operator and the comms stack
into labels the controller can reason about. Pulling labels from an
external standard (e.g. NATO medical triage) tempts misinterpretation:
the simulator's labels are not medical claims. Inventing labels also
risks reinventing what an existing standard already covers well.

## Decision

`nous` ships two internal vocabularies, both `StrEnum`s and both
documented as project-internal:

- `OperatorState`: `NOMINAL`, `ELEVATED`, `STRESSED`, `IMPAIRED`,
  `INCAPACITATED`. Derived from the biometrics estimator by
  `src/nous/state/operator_state.derive`.
- `CommsState`: `CONNECTED`, `LIMITED`, `DEGRADED`, `DENIED`. Derived
  from per-link estimates by `src/nous/state/comms_state.derive`.

Five operator levels and four comms levels are enough granularity for
the controller to choose a posture without being so granular that
boundary states get litigated.

## Consequences

Easier: the vocabulary is small enough that everyone calling into the
self-model layer agrees on what each label means. Mapping into an
external standard (if a deployment needs to) is a one-function
adapter.

Harder: the labels are not directly interoperable with TAK or other
mission stacks. The adapters under `src/nous/interop/` translate.

## Revisit triggers

- A deployment requires a STANAG-defined operator state ontology.
- The five levels prove too coarse for a scenario (e.g. fine-grained
  hydration tracking that does not map cleanly onto `ELEVATED`).
