# ADR 0059: comms_state CONNECTED requires every configured link healthy

- **Status:** Accepted
- **Date:** 2026-06-15
- **Authors:** rmednitzer
- **Builds on:** ADR 0006, ADR 0051

## Context

`comms_state.derive` summarises the per-link estimates into one label (CONNECTED
/ LIMITED / DEGRADED / DENIED). It reports CONNECTED only when every configured
link is connected and healthy (`len(healthy) == len(links)`, where `links` is
the full inventory). The 2026-06-14b audit (M-3) observed that a multi-link
profile with a backup link that has aged out or disconnected can therefore never
report CONNECTED, only LIMITED, even when the active link is perfectly healthy,
and asked for a deliberate decision between two meanings:

- "all configured links nominal" (current): the inventory is the denominator, so
  a dark backup drops the label out of CONNECTED.
- "all currently-connected links healthy": the connected set is the denominator,
  so a dark backup does not block CONNECTED as long as every up link is healthy.

The label is reporting-only. No FSM transition distinguishes CONNECTED from
LIMITED: the comms safety gate (`REQ_COMMS_LINK`) and the engine's link-mode
auto-degrade both key on DENIED, and the self-model situation read treats only
DENIED specially. So the choice affects the `comms_status` / self-model label and
telemetry, not a transition or a safety posture.

## Decision

CONNECTED keeps its "every configured link nominal" meaning: `derive` reports
CONNECTED only when every link in the inventory is connected and healthy, and a
disconnected or aged-out backup deliberately caps the report at LIMITED. The
rationale is legibility of the configured posture. A profile lists the links the
device is expected to have, so losing one is a real reduction in redundancy that
the top-line label should surface rather than hide. Reporting CONNECTED on a
healthy primary while a configured backup is dark would make the strongest label
mean "the link I happen to have up is fine," which understates the loss of a
configured fallback. LIMITED already carries "comms work, but not at the full
configured posture," whether the shortfall is a degraded active link or a missing
one; the reason string distinguishes the two.

The alternative (the connected-set denominator) was considered and rejected. It
is the more operationally forgiving reading, but because the label is
informational the conservative meaning costs nothing in transition behaviour
while giving the controller an honest redundancy signal. A comment on `derive`
records why the denominator is the inventory, and a regression pin
(`TestM3CommsConnectedRequiresAllConfiguredLinks`) asserts that a healthy active
link plus a disconnected backup reports LIMITED, so a future refactor cannot
silently relax the rule.

## Consequences

The reported comms label stays conservative: a device with redundant links
reports CONNECTED only with full redundancy intact, and a single dark backup is
visible as LIMITED. No behaviour changes (the code is unchanged beyond the
clarifying comment), so no existing test churns. The cost is that an operator who
regards a normally-dark backup as expected sees LIMITED rather than CONNECTED
during normal operation; the reason string names the shortfall, and a profile
that does not want a link counted toward the posture should not configure it as a
standing link. Closes BL-095.

## Revisit triggers

If a future profile models a link that is expected to be dark most of the time (a
satellite link raised only on demand), revisit whether such a link should be
excluded from the CONNECTED denominator, or introduce an explicit per-link
"optional" flag rather than flipping the global rule.
