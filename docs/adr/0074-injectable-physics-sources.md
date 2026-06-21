# ADR 0074: Injectable physics sources, the standalone-to-external seam

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0053, ADR 0072, ADR 0073

## Context

The moving-platform deepening added a procedural world (ADR 0072), a strapdown IMU,
and a nonlinear GNSS/INS EKF (ADR 0073). Each draws its physics from a narrow,
already-established injection seam rather than a hardwired source: the engine RNG
(`rng=`, ADR 0019) seeds every stochastic draw, the comms link budget reads the
device position through a lazy `position_fn` (ADR 0053), and the terrain it samples
arrives as an injected `terrain=` object (ADR 0072). The platform's own motion is a
seam too: the IMU senses whatever speed and heading the position subsystem is
commanded.

`nous` is and must stay standalone (LIMITATIONS L17): it cannot import a sibling
physics engine. But the original design question that motivated this work was
whether the twin could later be driven by an external embodied-physics simulator
without losing that property. This ADR records that the answer is yes, by seam, and
formalises the world half of it.

## Decision

Treat the physics inputs as injected sources behind narrow contracts, with an
in-tree standalone default for each, and formalise the world contract as a Protocol.

`subsystems/terrain.py` gains a `WorldSource` Protocol: `elevation(lat, lon)` and a
`path_profile` sampler, the two methods the comms link budget needs. The in-tree
`TerrainModel` (a seeded procedural field) is the default and satisfies it
structurally; the comms subsystem now types its `terrain` parameter as
`WorldSource`, so any conforming source, an out-of-tree adapter backed by an
external physics engine or a real elevation-tile dataset, drops in wherever the
`TerrainModel` is today without `nous` importing it.

The other seams already exist and are left as they are, now named together as the
boundary: the engine RNG (`rng=`), the device-position getter (`position_fn=`), and
the platform-motion commands (`set_velocity` / `set_motion`). An external driver
implements the sources; `nous` consumes the contracts. Nothing crosses the boundary
at import time, so the standalone constraint holds.

## Consequences

The "could an external embodied-physics simulator drive the twin?" question has a
documented, type-checked answer: implement `WorldSource` (and feed the existing
position and motion seams) from outside the tree, inject it, and the twin's comms,
terrain, and EKF run against it unchanged. The default stays the standalone
procedural world, so an unconfigured `nous` is exactly as it was. The seam is the
same discipline the RNG and position injections already use, so it adds one Protocol
and no runtime coupling.

This is documentation-and-contract work, not a new capability for the default twin:
no in-tree behaviour changes, and no external adapter ships here (that would be the
out-of-tree repository, kept separate by L17).

## Alternatives considered and rejected

- A single mega `PhysicsSource` Protocol bundling RNG, position, motion, and world.
  Rejected: the seams have different shapes and lifetimes (the RNG is a numpy
  Generator, position is a getter, motion is a command, world is a sampler); forcing
  them into one interface is less honest than naming the four narrow contracts that
  already exist.
- Importing the external engine under an optional extra. Rejected: it would make the
  dependency real (even if optional) and breach L17; the seam keeps the adapter
  out-of-tree.

## Revisit triggers

- An out-of-tree physics adapter is actually built (then this ADR is the contract it
  implements, and any gaps in the seam surface there).
- The position or motion seam needs the same Protocol formalisation the world seam
  got (then add `PositionSource` / `MotionSource` Protocols beside `WorldSource`).
