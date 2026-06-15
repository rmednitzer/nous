# ADR 0066: EMCON scheduled emission windows

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0047, ADR 0065

## Context

ADR 0065 gave the device a named EMCON posture: a profile lists the links
permitted to emit, and a send on a forbidden link is held in the
store-and-forward outbox rather than dropped. That models a steady silence (full
`silent`, or a restricted low-probability-of-intercept channel), but real
emission control is often scheduled rather than steady. A device under a
low-probability-of-detection regime transmits in short bursts on a fixed cadence
and stays quiet between them, so an observer sees brief, infrequent emissions
instead of a continuous signal. This is the next BL-060 increment the prior ADR
named, and it leans on the same outbox tie-in: traffic offered between bursts
must wait for the next window, not drop.

The clock is the design constraint. The window has to be evaluated against the
canonical simulation time so the schedule is deterministic and reproducible, and
survives a restart or a scenario time offset; the comms subsystem's own elapsed
counter is not that clock. ADR 0019's discipline is to inject `now_s` at the seam
rather than read an ambient clock, and every caller of the `tx` seam (direct
send, interop publish, outbox flush) already holds the engine's `state.ts_s`.

## Decision

A profile may carry a duty-cycle `window` alongside its `permit_links`:
`{ period_s, on_s, phase_s }`. The profile's links may emit only while
`(now_s - phase_s) mod period_s < on_s`, that is `on_s` seconds open out of every
`period_s`, and are silent the rest of the cycle. A window is registered only when
it is a genuine duty cycle (`period_s > 0` and `0 < on_s < period_s`); a malformed
or trivially always-open window is ignored and the profile behaves as unwindowed,
so a misconfiguration cannot silently black-hole all traffic (an operator who
wants steady silence uses `silent`).

The gate stays exactly where ADR 0065 put it, `CommsSubsystem.tx`, which now takes
an injected `now_s`. `Emcon.permits(link_id, now_s)` keeps the membership check and
adds the window test when the active profile has one; with no window, or no `now_s`
to place against the schedule, it is membership-only, so an unwindowed posture is
unchanged. A send in a closed window returns zero from `tx`, the same contract a
forbidden link already uses, so the BL-077 outbox holds the package and the
tick-driven flush ships it on the next open burst with no new plumbing. The
`emcon_status` read reports the active profile's `window` and whether it is
`emitting` at the current tick, plus the per-profile `windows` map, so the
schedule is legible to the controller.

The `window` key is an additive extension of the `comms.emcon` profile schema that
ADR 0065 introduced. It is the one high-blast touch this increment makes (the
profile schema), and it is backward compatible: a profile section without a
`window` is exactly the increment-1 behaviour.

## Consequences

A controller can impose a burst schedule and watch the device emit in windows and
hold its outbound packages between them, draining the backlog at each open burst.
The cost is a modulo test in the `tx` path (negligible) and threading `now_s`
through the three `tx` call sites, which aligns them with the clock discipline the
outbox already follows. The layer stays inert without a `comms.emcon` section and
under an unwindowed profile, so existing profiles and tests are unchanged; the
spot-core profile ships a demonstrative `lte_burst` window.

The window gates a whole profile uniformly: every permitted link shares one
schedule. Per-link schedules (a slow channel bursting on a different cadence than a
fast one) and irregular or multi-burst windows are deliberately out of scope here.
The posture, including the active profile, stays in-memory per ADR 0065; the
schedule is config-derived, so a restart resumes the same windows against the
restored clock.

## Revisit triggers

Per-link emission windows and explicit (non-duty-cycle) window lists are the
natural follow-ons if a scenario needs them. Metadata minimisation and a
first-class `denied` audit record carrying EMCON context remain the open BL-060
increments from ADR 0065. If an operator-set posture must survive a reboot, the
ADR 0064 persistence pattern applies to the active profile name.
