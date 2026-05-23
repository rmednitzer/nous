---
name: nous-scenario-walkthrough
description: Run a scenario YAML end to end and interpret the engine snapshots.
---

# Scenario walkthrough

1. List scenarios under `scenarios/`. Pick one whose `meta.description`
   matches the question.
2. `scenario_load` (BL-014, planned) will read the YAML and prime the
   engine. Until BL-014 lands, drive scenarios from the CLI:
   `uv run nous scenario scenarios/<name>.yaml`.
3. `scenario_resume` will run the engine forward; each tick the
   injectors mutate state per the timeline.
4. Sample `device_health`, `state_get`, and the relevant subsystem
   read tools at the cadence the scenario expects.
5. When the scenario completes, call `self_model_assess` to summarise
   capability outcomes (the layer wiring is BL-018; until then the
   tool returns the engine's `last_capabilities` dict).

If the scenario stalls (no FSM transitions for many ticks), check
`audit_summary` for refusals: the policy mode may be too tight, or
the FSM guards (ADR 0018) may be refusing transitions because the
thermal headroom or SoC context is below the configured threshold.
