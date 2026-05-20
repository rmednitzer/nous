---
name: nous-stpa-update
description: How to extend the STPA artefacts when a new hazard or constraint emerges.
---

# Updating the STPA

A new hazard surfaces in three ways: a scenario uncovers it, a code
review identifies a missing constraint, or a downstream consumer
reports a misleading output. In any case:

1. Add an entry to `docs/stpa/04-hazards.md` with a new `H-N` id and
   the linked loss.
2. Add the corresponding safety constraint to
   `docs/stpa/05-safety-constraints.md`.
3. If the hazard involves a controller action, extend
   `docs/stpa/07-unsafe-control-actions.md` and trace through to a
   loss scenario in `docs/stpa/08-loss-scenarios.md`.
4. File a backlog item (`BL-NNN`) for the derived requirement and add
   the row to `docs/stpa/09-derived-requirements.md`.
5. If the constraint requires changing a *contract* (policy, runner,
   audit, FSM, anthropic_client, estimator/interop base), open an
   ADR.

Keep the artefacts terse. STPA is a tool for thinking, not a
documentation deliverable.
