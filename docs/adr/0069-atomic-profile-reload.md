# ADR 0069: Atomic profile reload

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0019

## Context

The 2026-06-15 audit (`docs/audit-2026-06-15.md`, H-4 / BL-103) found that
`Engine.reload_profile` committed the new profile to `self.profile` and then
rebuilt the subsystems in place. `_load_profile` validates only the top-level
shape (`name`, `power`, `thermal`); a section it leaves untyped, such as a
non-mapping `comms`, passes the load and then crashes the subsystem constructor
mid-rebuild. The engine was then left in a mixed-generation state: a new profile
name and some new subsystems alongside the previous comms, position, sensors, and
biometrics, with no recovery path. The method's own docstring promised the
opposite, that the engine keeps the previous profile loaded on a malformed
profile.

## Decision

The rebuild is made atomic. `reload_profile` now constructs every subsystem from
the new profile into local variables first, and only after all of them succeed
does it commit the new profile name, profile, and subsystems to `self`. A
constructor that raises on a malformed section propagates the error with nothing
committed, so the engine keeps the previous profile and every previous subsystem
intact, exactly as the docstring promises. The estimator, failsafe, and
capability rebuild that follow read the committed subsystems and are unchanged;
they do not read the profile directly, so they cannot fail on a malformed section
once the subsystems have constructed.

This is the smallest fix that restores the contract: it defers the commit rather
than adding a separate validation pass. A `ProfileModel` that types every section
was the alternative, but it would couple the schema to each subsystem's
expectations and still not cover a subsystem that fails for a reason the schema
cannot express, whereas deferring the commit covers any construction failure
uniformly. The engine constructor is left as is: on first construction there is no
previous state to preserve, so a failure there simply aborts object creation.

## Consequences

A controller (or a scenario injector) that reloads a malformed profile now gets a
raised error and an engine that still runs on the profile it had, instead of a
torn engine that reports a new profile name over a half-rebuilt physics. The cost
is a second set of local names during the rebuild and a small divergence from the
constructor, which builds directly into `self`; the duplication between the two
construction paths is pre-existing and left for a future shared-helper refactor if
it proves worth the blast radius.

## Revisit triggers

Extracting a shared `_build_subsystems` helper used by both the constructor and
the reload would remove the duplication if the two paths drift. Building the DTN
mesh into a local as well would extend the atomic guarantee to the mesh, though
its config parsing already degrades gracefully on a malformed `dtn` section.
