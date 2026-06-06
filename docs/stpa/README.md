# STPA-Pro safety analysis

`nous` uses STPA-Pro (System-Theoretic Process Analysis, Leveson 2023)
as its safety analysis method. STPA treats safety as a control problem:
losses are emergent from inadequate control rather than from
component failure alone.

The artefacts follow the canonical numbered layout:

| File | Contents |
|------|----------|
| [01-purpose.md](01-purpose.md) | Why we are running an STPA on the simulator. |
| [02-system-boundary.md](02-system-boundary.md) | What is inside the system, what is outside. |
| [03-losses.md](03-losses.md) | Top-level losses (L-1 .. L-4). |
| [04-hazards.md](04-hazards.md) | Hazardous system states (H-1 .. H-8). |
| [05-safety-constraints.md](05-safety-constraints.md) | Safety constraints derived from hazards. |
| [06-control-structure.md](06-control-structure.md) | The control diagram (mermaid). |
| [07-unsafe-control-actions.md](07-unsafe-control-actions.md) | UCA table per controller. |
| [08-loss-scenarios.md](08-loss-scenarios.md) | Loss scenarios for the chosen UCAs. |
| [09-derived-requirements.md](09-derived-requirements.md) | Requirements that flow back into the backlog. |
| [10-fsm-constraints-mapping.md](10-fsm-constraints-mapping.md) | FSM transition to constraint to hazard traceability. |
| [11-coverage.md](11-coverage.md) | End-to-end coverage report: loss to requirement, with the test that pins each enforced requirement. |

The derived requirements are complete: every safety constraint (SC-1 .. SC-8)
carries at least one **enforced** derived requirement, and
[11-coverage.md](11-coverage.md) traces each loss end to end and names the test
that pins every enforced requirement (BL-044). The analysis stays a teaching
artefact for "how would we operate the real device?", not a certified safety
case (artefact 01, `LIMITATIONS.md` L16). Requirements cross-link to the backlog
(`docs/backlog.md`) and the governing ADR.
