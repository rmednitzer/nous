# ADR 0022: Runtime safety enforcer with structured result

- **Status:** Accepted
- **Date:** 2026-05-24
- **Authors:** rmednitzer
- **Builds on:** ADR 0009, ADR 0018

## Context

`docs/stpa/` enumerates safety constraints (SC-2 thermal headroom,
the low-power constraints, comms-state guards, the operator-state
escalation rules). ADR 0018 wired the FSM transitions to a per-trigger
guard predicate so SC-2 is enforced at the mode boundary. The rest of
the STPA constraints live in prose and in the FSM guard table, but
not as a runtime artefact a controller can observe.

A real-world example is the thermal throttle. SC-2 refuses MISSION
when junction temperature is over budget; the throttle itself is a
subsystem-level effect (`ThermalSubsystem.throttling`) that the
compute subsystem reads. There is no single chokepoint that records
"this safety constraint fired, here is the evidence, here is what was
clamped." A controller that wants to know whether the device entered
a safe-mode regime today has to crawl the audit log for inferred
patterns.

The shape that closes this gap is a single chokepoint whose every
check returns a structured `Result(approved, value, was_clamped,
violation_type, evidence)`. The enforcer carries a cumulative
violation counter; the STPA doc cross-references each constraint id
to a hazard. The runtime artefact (a `Result` value) is the bridge
between the constraint as written and the constraint as enforced.

The nous-specific extension is the tier-classified audit log. A
safety check that fires is already a high-blast-radius event; surfacing
it as an audit record is the canonical disposition.

## Decision

Add `src/nous/safety/enforcer.py` with two public types:

```python
@dataclass
class SafetyResult:
    approved: bool
    value: Any
    was_clamped: bool = False
    constraint_id: str = ""
    violation_type: str | None = None
    evidence: Mapping[str, Any] = field(default_factory=dict)


class SafetyEnforcer:
    def check(
        self,
        constraint_id: str,
        candidate: Any,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> SafetyResult: ...
```

`constraint_id` is one of the SC-N identifiers in
`docs/stpa/05-safety-constraints.md`. The enforcer owns a
`violation_count` per id and a total counter exposed through
`device_info`. Every `SafetyResult` is mirrored to the audit log
under a new `Tier.SAFETY` classification: a safety check never
mutates observable state, so it is adjacent to `READ_ONLY` on the
data-modification axis, but the fact of the check is itself a
distinct audit event that a controller should be able to query
without conflating it with ordinary reads. The exact integer
placement (a new value at the end of the enum vs. renumbering the
existing tiers) is left to the implementation PR, since `Tier` is an
`IntEnum` and the ordering matters to `policy.decide()`.

The FSM guards in ADR-0018 are the first caller. `request_transition`
constructs a `SafetyEnforcer` `check("SC-2", thermal_headroom_c,
evidence=...)`, threads the `SafetyResult` into the existing
`GuardDenied.reason`, and writes the audit line. The subsystem
throttle paths (compute, thermal) follow the same pattern when they
clamp.

The decision is intentionally narrow: this ADR governs the runtime
seam, not which constraints get enforced. The set of enforced
constraints stays in `docs/stpa/05-safety-constraints.md` and grows
through STPA refinement. A constraint is "enforced" only when a
`check()` site exists for it.

## Consequences

Easier: every STPA constraint that gets enforced has a runtime
artefact (audit record with `constraint_id`, evidence, clamped flag)
that a controller can query without log-scraping. The
violation-counter exposed via `device_info` lets the controller see
the safe-mode posture at a glance. STPA-Pro audit trails become a
mechanical join: pull every `Tier.SAFETY` audit record, group by
`constraint_id`, present.

Harder: `audit.py` grows a new tier classification; the
tier-classifier frozensets in `policy.py` need a new entry and the
`Tier` enum gains one value, with the integer placement chosen so
existing ordered comparisons in `policy.decide()` still hold. The
audit-log schema gains an optional `safety: SafetyResult` field,
versioned via ADR-0012. Existing constraints in the FSM guard table
all need a `constraint_id` so the audit join is unambiguous.

Alternatives rejected:

- **Inline checks at each subsystem.** Today's pattern. The
  constraint id and the evidence are not captured, so the audit log
  loses the trail.
- **STPA constraints as data only, no runtime enforcer.** Leaves the
  constraint as prose; a violation is observable only through the
  effect, not the cause.
- **A pytest fixture that asserts constraints, not a runtime
  enforcer.** Catches the constraint at test time but not on a
  deployed device.

## Revisit triggers

- The set of enforced constraints exceeds twenty and the per-id
  counter becomes unwieldy; consider a per-subsystem partition.
- A constraint requires evidence that does not fit
  `Mapping[str, Any]` (for example, a time-series window of recent
  observations).
- An external safety analyser (e.g. Polyspace) needs to consume the
  enforcer's constraint vocabulary; the id space may need a formal
  schema under `docs/stpa/`.
