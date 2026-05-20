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
| [04-hazards.md](04-hazards.md) | Hazardous system states (H-1 .. H-7). |
| [05-safety-constraints.md](05-safety-constraints.md) | Safety constraints derived from hazards. |
| [06-control-structure.md](06-control-structure.md) | The control diagram (mermaid). |
| [07-unsafe-control-actions.md](07-unsafe-control-actions.md) | UCA table per controller. |
| [08-loss-scenarios.md](08-loss-scenarios.md) | Loss scenarios for the chosen UCAs. |
| [09-derived-requirements.md](09-derived-requirements.md) | Requirements that flow back into the backlog. |

The STPA is treated as a *work in progress*; the v0.1 pass covers the
top losses, hazards, control structure, and a first pass at unsafe
control actions and loss scenarios. Derived requirements are partial
and cross-link to the backlog (`docs/backlog.md`) and any governing
ADR.
