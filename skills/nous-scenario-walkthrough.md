---
name: nous-scenario-walkthrough
description: Run a scenario YAML end to end and interpret the engine snapshots.
---

# Scenario walkthrough

1. List scenarios under `scenarios/`. Pick one whose `meta.description`
   matches the question.
2. `scenario_load` (T2) reads the YAML and runs it against the live engine.
   The default `mode="run"` advances through the scenario's tick budget
   inside the call and returns the structured run report. (The CLI path
   `uv run nous scenario scenarios/<name>.yaml` runs the same scenario
   outside MCP.)
3. To interleave reads while the scenario runs, load it with
   `mode="session"` instead: the call returns immediately and the timeline
   rides the live tick loop. `scenario_status` (T0) reads progress (fired
   steps, the scenario clock, the next pending step; once done it also
   carries the final snapshot). `scenario_pause` / `scenario_resume` (T1)
   freeze and unfreeze the scenario clock -- the device keeps ticking --
   and `scenario_reset` (T1) detaches the session so a new scenario can
   load (injections already applied persist). `tick_advance` (T1)
   fast-forwards simulated time by up to 600 ticks per call, advancing any
   active session deterministically instead of waiting wall-clock.
4. For an ad-hoc what-if without a YAML, `scenario_inject` (T2) fires a
   single injector against the live engine.
5. Sample `device_health`, `state_get`, and the relevant subsystem
   read tools at the cadence the scenario expects.
6. When the scenario completes, call `self_model_assess` to summarise
   capability outcomes; it returns one claim per capability with calibrated
   `p5`/`p50`/`p95` quantiles, a `confidence`, and the `drivers`.

If the scenario stalls (no FSM transitions for many ticks), check
`audit_summary` for refusals: the policy mode may be too tight, or
the FSM guards (ADR 0018) may be refusing transitions because the
thermal headroom or SoC context is below the configured threshold.
