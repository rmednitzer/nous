# ADR 0071: Self-model inference status reads the central point, with a degraded advisory

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0038, BL-035

## Context

The self-model situational read (`self_model_situation`, ADR 0038) colours each
capability claim with an advisory status. `_endurance_status` and
`_thermal_status` threshold on the conservative `cap.p5` (the 5th-percentile
lower band from the BL-035 Monte Carlo), while `_inference_status` thresholds the
critical floor on the central `cap.point`. AUDIT-2026-06-16 (BL-111) flagged the
inconsistency, and a second gap: a `degraded` inference status (compute throttled
while the point is above the floor) produced no recommendation line, where every
other degraded capability does.

The status thresholds are reporting-only. No FSM transition or safety gate reads
them (the `SafetyEnforcer` and the failsafe arbiter key on their own thresholds),
so this is a legibility question, not a safety one.

## Decision

Keep the central `cap.point` as the basis for the inference critical floor, and
document why it is deliberate rather than an oversight.

The inference floor (1 tok/s) is a breach test, not a margin test. It asks whether
local inference is effectively unavailable, that is, whether the expected
capability has collapsed to the floor. The honest reading of "has it collapsed" is
the central estimate, not the pessimistic tail: reading `p5 <= floor` would
escalate a healthy-but-uncertain estimate (point well above the floor, lower tail
grazing it) to `critical`, conflating uncertainty with collapse. The situation
layer already surfaces uncertainty through the separate `watch` branch
(`confidence < _LOW_CONFIDENCE`), so a healthy-but-uncertain inference reads
`watch`, which is the correct signal. Endurance and thermal use `p5` because theirs
are margin questions ("even pessimistically, is there enough headroom"), a
different question with a different right answer.

Close the recommendation gap with a behaviour change: a `degraded` inference status
now emits its own advisory line, the way endurance and thermal already do. The
trigger for `degraded` is `compute.throttled`, which is true whenever delivered
load is clipped below the request, by the thermal throttle ceiling or by an FSM
mode-load ceiling (`engine.py` sets a per-mode ceiling). The advisory therefore
names the throttle generically rather than assuming thermal: a mode-ceiling
throttle is not covered by the thermal advisory, so without this line a throttled
inference could read `degraded` with no explanation at all.

## Consequences

The three capability statuses now rest on a documented, intentional basis: `p5` for
the two margin questions, `point` for the one breach question, with uncertainty
routed to `watch` in every case. A controller reading a `degraded` inference now
gets a line explaining it regardless of whether the throttle is thermal or
mode-imposed, so the recommendations are consistent across all monitored
capabilities. The change is additive and reporting-only; no estimator, FSM, or
safety path moves.

The rejected alternative is to switch `_inference_status` to `p5` for surface
consistency. It was rejected because it answers the wrong question for a breach
floor and would convert the existing `watch`-for-uncertainty signal into spurious
`critical` alarms.

## Revisit triggers

- A consumer begins keying a control or safety decision on an advisory status (then
  the basis becomes load-bearing and is revisited as a safety contract, not a
  legibility one).
- The inference floor stops being a pure breach test (e.g. a graded inference SLA
  with a margin band), at which point the margin-versus-breach split is
  reconsidered.
