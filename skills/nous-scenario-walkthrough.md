---
name: nous-scenario-walkthrough
description: Run a scenario YAML end to end and interpret the engine snapshots.
---

# Scenario walkthrough

1. List scenarios under `scenarios/`. Pick one whose `meta.description`
   matches the question.
2. `scenario_load` (L1) reads the YAML and primes the engine.
3. `scenario_resume` runs the engine forward; each tick the injectors
   mutate state per the timeline.
4. Sample `device_health`, `state_get`, and the relevant subsystem
   read tools at the cadence the scenario expects.
5. When the scenario completes, call `self_model_assess` to summarise
   capability outcomes.

If the scenario stalls (no FSM transitions for many ticks), check
`audit_summary` for refusals -- the policy mode may be too tight.
