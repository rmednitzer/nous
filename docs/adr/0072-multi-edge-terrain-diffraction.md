# ADR 0072: Multi-edge terrain diffraction over a procedural world

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0019, ADR 0053, ADR 0054

## Context

BL-048 (ADR 0053) gave each propagation link a first-order link budget; BL-088
(ADR 0054) added a single knife-edge diffraction term from one configured
obstruction (`obstruction_distance_m` / `obstruction_height_m`). A real path
between the device and a peer crosses many ridges, not one. BL-089 is the
remaining terrain story: lift the single knife edge to a digital-elevation-model
path profile and a multi-edge diffraction method.

Two constraints shape the design. `nous` is standalone (LIMITATIONS L17), so it
cannot fetch an elevation dataset. And the per-tick cost must stay under the tick
budget (the BL-073 concern), so the path sampling must be cheap and bounded.

## Decision

Add a deterministic procedural terrain model and a Bullington multi-edge
diffraction method, both additive and opt-in per link.

`subsystems/terrain.py` holds a `TerrainModel`: a seeded sum of a handful of
sinusoidal ridge components, drawn once at construction from a
`numpy.random.Generator` (ADR 0019), giving a smooth, repeatable elevation field
bounded by the configured relief. It exposes `elevation(lat, lon)` and a
`path_profile` sampler along the great circle to a peer. This is the standalone
substitute for a fetched DEM: the same `elevation` / `path_profile` interface
could be backed by a real elevation-tile loader out of tree without `nous`
taking a data dependency, the seam discipline the position and RNG injections
already use.

`subsystems/propagation.py` gains `bullington_diffraction_db`: the ITU-R P.526
Bullington construction over the sampled path. It takes the steepest obstacle
seen from each endpoint, intersects their rays to form one equivalent knife edge,
and applies the shared Fresnel kernel (`_fresnel_diffraction_loss_db`, factored
out of the single knife edge so both share one `J(v)`). With a single interior
obstacle it reduces exactly to the BL-088 single knife edge, since the Bullington
point lands on that obstacle and `2 d / (d1 d2) == 2 (1/d1 + 1/d2)` when
`d1 + d2 = d`.

A link opts in with `propagation.use_terrain: true` and a `terrain_samples`
count; the engine builds the `TerrainModel` from an optional top-level `world`
profile section and threads it into the comms subsystem beside the existing `rng`
and `position_fn` injections. `solve_link_budget` runs the multi-edge method over
the sampled profile when the link opts in and a terrain model is present, and the
single knife edge otherwise. Every new field defaults off, so a link with no
`world` section or `use_terrain: false` is byte-for-byte the BL-088 behaviour.

## Consequences

Comms scenarios now degrade behind real terrain: a ridge between the device and a
peer blocks the link, and moving the device changes the sampled path so the
diffraction varies position to position rather than as a fixed offset, exactly the
legibility the twin exists to provide. The terrain is deterministic under the
profile seed, so a scenario reproduces. The cost is one new module and one pure
function; the per-tick work is sampling N points (default 16) times a handful of
ridge components, well under the tick budget.

The terrain is procedural, not surveyed, so it does not match any real location;
the model demonstrates the physics, not a specific theatre. Bullington is a single
equivalent edge, so it is conservative against the more accurate Deygout sub-path
recursion for closely spaced peaks.

## Alternatives considered and rejected

- A real DEM-tile loader (SRTM, Copernicus). Rejected for now: it adds a dataset
  dependency that breaks the standalone constraint. The interface is left so an
  out-of-tree loader can implement it.
- Multiple explicit obstructions (a list of knife edges) instead of a sampled
  field. Rejected: it delivers the multi-edge math but not the DEM-path-profile
  intent of BL-089, and a moving device would not see the terrain change.
- Deygout over Bullington. Deferred: Bullington is O(N) single-pass and reduces
  exactly to the existing single edge; Deygout is the accuracy refinement.

## Revisit triggers

- A scenario needs a specific real terrain (then an out-of-tree DEM loader
  implements the `TerrainModel` interface).
- Closely-spaced multi-peak paths need better accuracy (then Deygout replaces or
  augments Bullington).
- Frequency-selective fading is needed (a tapped-delay-line channel rather than
  the flat Rician fade), the remaining BL-089 sub-feature deferred here.
