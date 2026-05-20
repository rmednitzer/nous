# ADR 0015: APU is strictly auxiliary; the primary battery is the sole bus

- **Status:** Accepted
- **Date:** 2026-05-20
- **Authors:** rmednitzer
- **Builds on:** ADR 0003, ADR 0010

## Context

The auxiliary power unit covers five distinct sources: a solar panel
with an MPPT front end, a methanol fuel cell, a vehicle tether
connection, a USB-C PD-in port, and a hand-crank generator. Each
source could in principle bypass the primary Li-ion pack and feed
compute directly. Doing so would let the simulator model a "battery
removed, running off solar" posture, at the cost of a much more
involved power-flow graph.

The alternative, and the path the v0.1 simulator takes, is to treat
every APU source as a charge input to the primary battery. Compute,
sensors, comms, and accessories pull from the battery; the APU only
ever charges it.

## Decision

The primary Li-ion pack is the sole power bus. Every APU source sums
into a single ``ApuSubsystem.total_w``, which the engine offers to
``PowerSubsystem.set_charge_w`` each tick. The bus regulator (the
power subsystem's ``charge_limit_w``) clamps the accepted charge; the
offered value is preserved so the controller can see how much APU
power was clipped.

This design implies:

- The APU never powers compute directly. Removing the battery puts
  the device offline regardless of how many APU sources are
  connected.
- The APU is always additive. There is no negotiation between
  sources, no fallback chain, no priority order.
- The bus regulator's clipping behaviour is observable. Callers can
  ask the power subsystem for ``charge_offered_w`` and
  ``charge_accepted_w`` and reason about under-utilised APU
  capacity.

## Consequences

Easier: the power-flow model has one node (the battery). Every
estimator and self-model rule reduces to "what does the battery look
like". Endurance estimates use ``load_w - charge_accepted_w`` without
having to reason about which source is feeding which bus.

Harder: scenarios that legitimately want to run on AC alone (wall
charger powering compute while the battery is removed for cooling or
replacement) cannot be expressed. A future ADR can revisit this if
the use case appears.

Alternatives rejected:

- A full multi-bus power graph with priority routing. Strictly
  superior in fidelity, strictly worse in legibility. The simulator
  prioritises legibility.
- A dual-mode "primary bus selector". Same legibility cost; the FSM
  would need to track which bus was active.

## Revisit triggers

- A scenario requires AC-only operation (battery removed or under
  thermal cooldown), or a workload too large for the charge limit to
  be feasibly served by APU + battery combined.
- A new APU source (e.g., a kinetic harvester, a thermoelectric
  generator) cannot reasonably be modelled as a charge contributor.
