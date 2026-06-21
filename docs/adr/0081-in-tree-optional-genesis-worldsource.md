# ADR 0081: in-tree optional Genesis WorldSource adapter

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0053, ADR 0072, ADR 0074
- **Amends:** ADR 0074 (the "optional extra is out, keep the adapter out-of-tree" alternative)

## Context

ADR 0074 formalised the `WorldSource` Protocol (`elevation`, `path_profile`) as the
world seam and recorded that an external embodied-physics simulator could drive the
twin by implementing it from outside the tree. It deliberately rejected one
alternative: "importing the external engine under an optional extra ... it would
make the dependency real (even if optional) and breach L17; the seam keeps the
adapter out-of-tree." Its revisit trigger was "an out-of-tree physics adapter is
actually built."

The adapter is now wanted, and the maintainer's call is to ship it in-tree rather
than as a separate repository: a `WorldSource` backed by a headless Genesis
(`genesis-world`) rigid-body scene, so the comms link budget and the EO/IR
line-of-sight can run against an engine-simulated world instead of the procedural
`TerrainModel`. That reverses the specific alternative ADR 0074 rejected, so this
ADR records the decision and the reasoning, and reconciles it with the standalone
constraint L17 the original rejection was protecting.

## Decision

Ship `nous.subsystems.genesis_world.GenesisWorldSource` in-tree as an opt-in
adapter, with `genesis-world` a manual, unlocked dependency, structured so the
standalone default is preserved exactly:

The module is never imported by the core import graph (`subsystems/__init__.py`
imports only `base`; no engine, subsystem, or tool imports it), and it imports
`genesis` lazily inside the constructor with a clear "install genesis-world"
error when it is absent. So an unconfigured `nous` neither installs, imports, nor
references a physics engine: `import nous` and the whole test suite run
engine-free, and the only cost when it is missing is that constructing the
adapter raises. `genesis-world` is intentionally not a `nous` extra: CI runs `uv
sync --all-extras`, which would otherwise pull the heavy GPU stack (torch,
mujoco) into every run and into the lock, so it is a documented manual install
and the lock and CI stay engine-free. The mypy `genesis.*` override keeps the
lazy import strict-clean without the package installed.

The adapter mirrors `TerrainModel`'s equirectangular projection and haversine
ground distance exactly, so it is a structural drop-in wherever a `TerrainModel` is
injected (`isinstance(src, WorldSource)` holds). `elevation` / `path_profile` are
pure reads of the height field Genesis built (`geoms[0].metadata["height_field"]`),
captured once at build, so they cost no per-query physics step and report the same
surface the rigid-body physics rests a body on. The optional position / motion seam
(`platform_lla`, `step`, `position_fn`) feeds the existing comms / EO-IR
`position_fn` contract from a simulated body, completing the "external simulator
drives the twin" path ADR 0074 described. The projection, interpolation, and path
sampling are factored into pure functions unit-tested without the extra; the
scene-build path is gated on `genesis` being importable.

## Consequences

The out-of-tree-only stance of ADR 0074 is relaxed: the adapter that exercises the
seam now lives, is tested, and is versioned alongside the contract it implements, so
a change to `WorldSource` and its adapter move together and the adapter is
discoverable rather than living in a separate repository. The seam ADR 0074 defined
is unchanged and is what the adapter implements; this ADR changes only where the
adapter lives.

The cost ADR 0074 named, a real (even if optional) dependency, is softened by
keeping `genesis-world` a manual, unlocked install rather than a locked extra: the
lock and CI stay engine-free, and the only in-tree footprint is the adapter module
and a mypy ignore rule. L17 is honoured in substance, the default twin is
byte-for-byte the standalone twin, the core never imports an engine, and nothing
resolves a physics engine into the lock, so the literal "no physics engine anywhere
in the project, even optionally" reading is loosened only to "the adapter source
lives in-tree." That trade is the maintainer's explicit choice (in-tree
discoverability and co-evolution over strict repository separation). Genesis is
heavy (torch, a GPU-oriented sim) and is not installed in CI, so the engine-backed
tests skip there and the adapter's scene path is validated where `genesis-world` is
present, not in the default pipeline.

## Alternatives considered and rejected

- Keep it out-of-tree, as ADR 0074 decided. Rejected here by maintainer choice: the
  adapter and the contract drift apart in separate repositories, and the adapter is
  less discoverable; the optional-extra structure recovers most of the L17 guarantee
  (engine-free default and core import graph) without that cost.
- A hard (non-optional) dependency. Rejected: that would breach L17 outright and pull
  a heavy GPU sim into every install; the manual install keeps it opt-in.
- A formal `nous[genesis]` extra in `pyproject.toml`. Rejected: CI runs `uv sync
  --all-extras`, so a declared extra would pull torch, mujoco, and the GPU stack into
  every CI run and into the lock, for tests that are meant to skip; an unlocked manual
  install keeps the lock and CI engine-free.
- Re-query Genesis per `elevation` call (raycast). Rejected: the built height field
  is readable as an array, so a bilinear read is O(1) with no physics step and is
  numerically identical to what the physics uses.

## Revisit triggers

- The position / motion seam needs the `PositionSource` / `MotionSource` Protocol
  formalisation ADR 0074 anticipated (then add them beside `WorldSource` and have the
  adapter implement them explicitly).
- A second external engine adapter arrives (then factor the shared projection and
  path-sampling helpers into a small `worldsource` support module).
- The optional-dependency cost outweighs the in-tree benefit (then this ADR is the
  one to supersede, returning the adapter out-of-tree per ADR 0074).
