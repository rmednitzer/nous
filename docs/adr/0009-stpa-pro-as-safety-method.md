# ADR 0009: STPA-Pro as the safety analysis method

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** n/a

## Context

A backpack inference appliance has obvious safety questions: thermal
runaway near the operator's body, false confidence in the self-model
during an incapacitation event, lossy comms during a critical hand-off.
Classical safety methods (FMEA, FTA) are component-oriented and miss
emergent control failures, which is exactly the failure mode that
matters when an AI controller is in the loop.

## Decision

`nous` uses STPA-Pro (System-Theoretic Process Analysis, Leveson 2023)
as the safety analysis method. Artefacts live in `docs/stpa/` and follow
the numbered layout: `01-purpose.md`, `02-system-boundary.md`,
`03-losses.md`, `04-hazards.md`, `05-safety-constraints.md`,
`06-control-structure.md`, `07-unsafe-control-actions.md`,
`08-loss-scenarios.md`, `09-derived-requirements.md`.

Derived requirements cross-reference the backlog (`BL-NNN`) and any
governing ADR. The STPA is treated as a *work in progress*; v0.1 covers
the first pass.

## Consequences

Easier: emergent control failures (the controller mis-reading the
self-model, the operator over-trusting a degraded link estimate) have a
home in the analysis. The derived-requirement column drives the
backlog.

Harder: STPA is heavier than FMEA for component-level reasoning. The
artefacts must be kept current as the simulator evolves.

## Revisit triggers

- A scenario uncovers a hazard not in `04-hazards.md`.
- A regulator asks for a specific method (e.g. ARP 4761) for a deployed
  use case.
