# ADR 0003: Hardware-profile YAML as the source of truth

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0001

## Context

A backpack inference appliance is parameterised by dozens of curves:
battery Wh, Peukert coefficient, compute power across load fractions,
junction temperature limits, sensor noise standard deviations, link
envelopes. Putting those numbers in code locks the simulator to one
device. Putting them in a database makes diff review awkward. Putting
them in YAML keeps them reviewable and lets profile authors propose a
new device without touching Python.

## Decision

Every numeric curve and limit lives in `profiles/<name>.yaml`. Code reads
the YAML at engine construction; the engine never writes a profile.
`jetson-agx-orin.yaml` is the reference profile; other profiles
(`jetson-orin-nx.yaml`, `pi5-hailo.yaml`, `spot-core.yaml`) inherit the
same schema with smaller numbers.

The schema is documented in `docs/hardware-profiles.md`. The L1 milestone
adds a Pydantic model that validates profiles at load time and emits a
JSON Schema via `scripts/gen_schemas.py`.

## Consequences

Easier: new hardware lands as a YAML PR with a small docs entry. Diffs
focus on numbers, not code.

Harder: schema evolution must be backward compatible across the v0.x
window. The Pydantic model needs explicit defaults and migrations are
not free.

Alternatives rejected:

- Embedding the curves in Python dataclasses. Better for type safety,
  worse for review and for third-party contributions.
- A binary format. Better for fidelity, worse for everything else.

## Revisit triggers

- A profile needs to carry binary calibration tables (e.g. a measured
  battery discharge surface). Then split tables out next to the YAML.
- Schema churn exceeds a small number of breaking changes per release.
