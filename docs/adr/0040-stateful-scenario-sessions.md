# ADR 0040: Stateful scenario sessions and deterministic tick stepping

- **Status:** Accepted
- **Date:** 2026-06-09
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0024, ADR 0027, ADR 0033

## Context

The scenario runner is a synchronous one-shot: `run_scenario` drives the
engine through the whole tick budget inside the `scenario_load` call and
returns a report. That blocks the MCP call for the scenario's duration, and
it leaves four forward-classified names (`scenario_status` T0,
`scenario_pause` / `scenario_resume` / `scenario_reset` T1) with nothing to
act on, a deferral ADR 0033 recorded explicitly. `tick_advance` (T1) was
deferred in the same list because a bare `Engine.tick()` wrapper looked like
a race against the process-scoped tick loop (ADR 0024). The 2026-06-06 audit
named registering these verbs the residual recommendation.

The missing piece was an execution shape in which a scenario advances with
the engine rather than driving it. The engine already has exactly one tick
cadence owner per deployment (the `nous serve` tick loop, a test calling
`tick()`, or nothing at all under `build_app`), so a scenario that observes
ticks instead of generating them composes with all three.

## Decision

`Engine` gains a tick-hook seam: `add_tick_hook` / `remove_tick_hook`
register per-tick observers called at the end of `tick()` with the settled
`TickContext`. A raising hook is contained and counted on
`tick_hook_errors` (surfaced in `snapshot()`), because an observer bug must
never kill the tick the auto-safing spine rides (ADR 0027).

`nous.scenarios.session.ScenarioSession` (BL-071) rides that seam. It
reuses the loader, the injectors, and the runner's record helpers, so a
fired step is reported identically by both execution surfaces; `at_min: 0`
steps fire at the load boundary exactly as the one-shot runner fires them.
Pause freezes the scenario clock, never the device: a paused session simply
stops consuming ticks, so steps stop firing and the budget stops counting,
while the engine keeps living. The session detaches itself when the budget
completes and freezes a completion snapshot, so its report describes the
device at scenario end even though the live loop ticks on. One session
exists at a time, held process-scoped on `Nous` (the ADR 0024 pattern), so
it survives stateless-HTTP requests; a finished session is cleared by the
next load.

One timing property carries over from the one-shot runner unchanged: a
hook-fired injection lands after the tick's auto-safing and post-tick
finiteness checks, so the safety layer evaluates it on the next tick (at
most one tick interval later). The one-shot runner has the identical lag
(it fires injectors after `engine.tick()` returns), so the two execution
surfaces are equivalent under the STPA constraints.

The tool surface registers the already-classified verbs in
`tools/scenarios.py`: `scenario_load` gains `mode="session"` (the default
`mode="run"` is byte-compatible with the historical report), and
`scenario_status` / `scenario_pause` / `scenario_resume` / `scenario_reset`
read and control the session. `scenario_reset` clears the session, not the
engine: injections already applied persist, which is the asymmetry that
keeps load at T2 while reset is T1. `tick_advance(n)` registers as a bounded
cooperative step (1 to 600 ticks per call, yielding to the event loop every
50): tools and the tick loop share one event loop and `Engine.tick()` never
awaits, so a tool-driven tick cannot interleave with a loop-driven one; the
only effect is simulated time advancing faster than wall clock, which is
the tool's purpose. A tick costs about a millisecond on the reference
profile, so the periodic yield keeps a maximal advance from monopolising
the server. No policy change; the surface grows from thirty-seven to
forty-two.

## Consequences

A controller on the stateless HTTP transport can now start a scenario,
interleave reads while it runs in real time, pause it to inspect a
transient, and fast-forward it deterministically with `tick_advance`
instead of waiting wall-clock minutes. The composition is the payoff:
`tick_advance` advances any active session because the session observes
ticks, whatever produces them. The ADR 0033 deferral list shrinks to names
that stay unregistered by design.

Alternatives rejected:

- **A background task driving ticks for the session.** A second tick driver
  races the process loop for real (double cadence), needs lifecycle plumbing
  through the lifespan, and breaks the one-owner-of-time property that makes
  `tick_advance` safe.
- **Pausing the tick loop for `tick_advance`.** A pause seam on the loop
  would let a controller freeze the device, which auto-safing (ADR 0027)
  must not allow; bounded extra ticks are reversible in the T1 sense, a
  frozen plant is not.
- **A `scenario_run` name returning a session handle.** The verbs were
  already classified under `scenario_load`'s umbrella plus the four control
  names; adding a new name would touch `policy.py` for no gain over a
  `mode` parameter.

## Revisit triggers

- A need for concurrent scenario sessions (today: one, by design).
- A wall-clock-coupled scenario (e.g. real-time operator interaction) that
  cannot express itself as tick-relative `at_min` offsets.
- Scenario `expectations` evaluation, which would want a hook on session
  completion.
- Tick cost growing past ~1 ms on the reference VM (the Monte Carlo
  capability refresh dominates it today; BL-073), which would argue for a
  smaller `tick_advance` bound or a tighter yield interval.
