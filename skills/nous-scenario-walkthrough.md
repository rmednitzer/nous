---
name: nous-scenario-walkthrough
description: Run a scenario YAML end to end and interpret the engine snapshots.
---

# Scenario walkthrough

1. List scenarios under `scenarios/`. Pick one whose `meta.description`
   matches the question.
2. `scenario_load` (T2) reads the YAML and runs it against the live engine,
   advancing through the scenario's tick budget and returning a structured
   run report. (The CLI path `uv run nous scenario scenarios/<name>.yaml`
   runs the same scenario outside MCP.)
3. `scenario_load` runs the timeline to completion; for an ad-hoc what-if
   without a YAML, `scenario_inject` (T2) fires a single injector against
   the live engine.
4. Sample `device_health`, `state_get`, and the relevant subsystem
   read tools at the cadence the scenario expects.
5. When the scenario completes, call `self_model_assess` to summarise
   capability outcomes; it returns one claim per capability with calibrated
   `p5`/`p50`/`p95` quantiles, a `confidence`, and the `drivers`.

If the scenario stalls (no FSM transitions for many ticks), check
`audit_summary` for refusals: the policy mode may be too tight, or
the FSM guards (ADR 0018) may be refusing transitions because the
thermal headroom or SoC context is below the configured threshold.
