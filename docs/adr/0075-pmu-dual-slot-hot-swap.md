# ADR 0075: PMU/PDU bus regulation and dual-slot battery hot-swap

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Supersedes:** ADR 0015
- **Builds on:** ADR 0010, ADR 0019

## Context

ADR-0015 made the primary Li-ion pack the sole power bus: every APU source summed
into `ApuSubsystem.total_w`, the engine offered it to `PowerSubsystem.set_charge_w`,
and the power subsystem's own `charge_limit_w` clamped the accepted charge. That
ADR's revisit triggers named exactly the posture this work needs: a scenario where
the battery is removed for replacement, which the sole-bus model cannot express.

BL-005b adds a power-management unit that owns the bus regulation and a second
battery slot, so the twin can model a dual-slot hot-swap: the inactive pack removed
without collapsing the bus, and the PMU arbitrating which pack powers the load.

## Decision

Introduce `PmuSubsystem` and move the bus regulation onto it; supersede the sole-bus
part of ADR-0015 with a dual-slot, PMU-arbitrated bus.

The PMU owns the charge regulation that used to live on the battery: a
`charge_limit_w` clamp (defaulting to the legacy `power.charge_limit_w`, so existing
profiles keep their bus limit) plus a CC/CV taper that backs the accepted charge off
as the active pack passes the `cv_soc_pct` knee toward full, the standard Li-ion
profile. `PowerSubsystem.set_charge_w` no longer clamps; it records the regulated
charge the PMU hands it. The controller reads offered-versus-accepted at the PMU
now, not the battery.

The PMU holds two slots, a primary (always present) and an optional secondary (an
inert default; a `pmu.secondary` profile section enables it). One slot is active and
powers the load; each tick the engine routes the load and the regulated charge to
the active pack, then the PMU arbitrates: when the active pack is exhausted it hands
the bus to a charged standby, keeping the device alive across the swap. The inactive
slot can be removed (`remove_slot`) and a fresh pack inserted (`insert_slot`) without
interrupting the active bus; removing the active slot is refused (it would collapse
the bus). The engine's `self.power` reference follows the active pack, so
`power_status` and the power estimator read whichever slot is on the bus.

A `pmu_status` read tool (T0, added to the policy read-only set) surfaces the charge
limit, the CC/CV mode, the offered-versus-accepted charge, the active slot, and the
slot presence and swap count.

## Consequences

The simulator can now express battery hot-swap: a depleted primary handed off to a
charged secondary with no bus collapse, and the standby pack pulled and replaced
while the device runs. The charge legibility (offered versus accepted, the CC/CV
stage) is now a first-class PMU read. Existing single-slot profiles are unchanged:
the PMU defaults to one slot with the same charge limit the battery used to apply,
so the engine-level charge behaviour is identical.

The cost is one orchestration subsystem between the APU and the battery, and a
moving `self.power` reference. The power estimator sees a discontinuity when the
active pack switches (a new pack's SoC); its innovation gate and reset absorb it (a
swap is a genuine discontinuity), so the estimate re-converges on the new pack.

Easier than the rejected full multi-bus graph: there is still exactly one active bus
node at a time, so endurance and the SC-8 reserve gate still reason about "the active
pack" without a power-flow graph.

## Alternatives considered and rejected

- Keep ADR-0015 (sole bus, no hot-swap). Rejected: the revisit trigger fired (the
  hot-swap posture is the BL-005b deliverable).
- Leave the clamp on the battery and add the PMU as a thin layer above it. Rejected:
  two owners of the charge limit is the ambiguity BL-005b set out to remove; the
  clamp belongs in one place, the PMU.
- A full N-slot battery bank with parallel draw. Rejected for v0.1: two slots with a
  single active pack covers the hot-swap use case and keeps the one-active-bus
  legibility; N parallel packs is a power-flow graph again.

## Revisit triggers

- Parallel draw from both slots (load-sharing) is needed, not just hot-swap.
- A slot needs its own charge controller (independent CC/CV per pack) rather than the
  single active-pack regulator.
