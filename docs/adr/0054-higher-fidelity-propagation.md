# ADR 0054: Higher-fidelity comms propagation (path loss, diffraction, noise, antenna, fading)

- **Status:** Accepted
- **Date:** 2026-06-14
- **Authors:** rmednitzer

## Context

ADR 0053 (BL-048) gave a comms link a first-order link budget: a Friis
free-space path loss with a fixed exponent of two, a single constant excess-loss
margin, a per-link constant noise floor, isotropic antenna gains, and a
log-normal shadowing draw. That is enough to make link quality depend on range,
but it ignores the propagation environment (free space is the most optimistic
case), any discrete terrain obstruction, antenna pointing, and the fast fading a
real radio sees. BL-088 raises the fidelity.

The full BL-088 horizon is broad (terrain raytracing over a DEM, multipath,
antenna patterns, a thermal-noise floor, mesh routing). This increment takes the
five that are tractable without new data dependencies and that compose cleanly
over the ADR 0053 link budget. DEM-driven terrain and mesh routing stay out: the
former needs an elevation dataset, the latter belongs in the BL-056
delay-tolerant-networking layer rather than the link budget.

## Decision

Every addition is an optional `LinkPropagation` field whose default reproduces
ADR 0053 exactly, so a link that does not opt in is byte-for-byte unchanged and
the existing suite stays green. The five dimensions:

1. **Log-distance path-loss exponent.** The path loss becomes
   `FSPL(1 m, f) + 10 * n * log10(d)`, where `n` is a configurable
   `path_loss_exponent`. `n = 2.0` (the default) is free space; `2.7` to `3.5`
   is urban; `4` and above is obstructed or forested. This is the single largest
   realism gain: attenuation now reflects the environment, not just the geometry.

2. **Single knife-edge diffraction.** An optional obstruction
   (`obstruction_distance_m` along the path, `obstruction_height_m` above sea
   level) adds the Fresnel-Kirchhoff knife-edge loss `J(v)` from the standard ITU
   approximation, where the diffraction parameter `v` comes from the
   obstruction's height above the line of sight. This models a ridge between the
   device and its peer without a DEM. No obstruction means no loss.

3. **kTB thermal noise floor.** When a `channel_bandwidth_hz` (and optional
   `noise_figure_db`) is given, the noise floor is computed as
   `-174 dBm/Hz + 10 * log10(B) + NF` rather than read from the per-link
   constant, so the SNR is physically grounded. Absent the channel bandwidth, the
   constant `noise_floor_dbm` is used (ADR 0053 behaviour).

4. **Directional antenna pattern.** When an `antenna_boresight_deg` is given, the
   device antenna gain rolls off with the off-boresight angle to the peer: a
   parabolic-in-dB main lobe (`-3 dB` at the configured half-beamwidth) floored
   at a back-lobe `antenna_front_to_back_db`. The bearing to the peer comes from
   the geometry. No boresight means an isotropic antenna (no roll-off).

5. **Rician multipath fading.** When a `rician_k_db` is given, a fast-fading draw
   (a Rician envelope with that K-factor, Rayleigh at `K = 0`) is added to the
   shadowing draw each tick. The draw comes from the engine RNG (ADR 0019), so it
   is deterministic under a seed; the caller draws it and passes it in, keeping
   the budget functions pure. No K-factor means no multipath.

`solve_link_budget` keeps its signature except for one new optional `fast_fade_db`
argument (the second stochastic draw, alongside `shadowing_db`); the other four
upgrades are read from the `LinkPropagation`. `subsystems/comms.py` draws the
fast-fade sample in `_apply_propagation` and is otherwise unchanged: it still
calls `solve_link_budget`, and the result still feeds the existing
`rssi_dbm` / `loss_pct` / `capacity_bps` fields, so the whole observation to
filter to `derive` to FSM pipeline is untouched.

## Consequences

Link quality now reflects the environment (a forest link at `n = 3.5` degrades
far sooner than free space), a discrete ridge (the diffraction loss appears the
moment the obstruction breaks the line of sight), antenna pointing (turning away
from the peer drops the gain), a real noise floor (a wider channel raises the
floor and lowers the SNR), and fast fading (a low K-factor adds tick-to-tick
variance the controller's estimator must ride out). All of it surfaces through
the same `comms_status` diagnostics and the same `comms_state` the FSM reads.

The inert-by-default rule keeps the blast radius small: the change is confined to
`subsystems/propagation.py` (additive functions and `LinkPropagation` fields),
the `LinkBudget` diagnostics, a one-argument addition to `solve_link_budget`, the
fast-fade draw in `subsystems/comms.py`, and the profile schema (optional fields,
a patch `schema_version` bump per ADR 0007 / ADR 0012, the ADR-gated surface).
The reference and demo profiles that do not set the new fields are unchanged.

Alternatives rejected. A full DEM-driven terrain model (multi-obstacle
raytracing, diffraction over an elevation profile) was rejected for this
increment because it needs an elevation dataset and a tile loader, a data and
performance effort out of proportion to a single knife edge, which already
captures the dominant obstruction case. A 3GPP three-sector antenna pattern was
rejected in favour of the simpler parabolic-in-dB lobe because the twin does not
need standards-exact sidelobes, only a smooth, monotone roll-off a controller can
reason about.

## Revisit triggers

- A scenario needs multi-obstacle terrain or a real elevation profile: the single
  knife edge is lifted to a DEM-driven path (Deygout or Bullington multi-edge),
  the remaining BL-088 terrain work.
- Frequency-selective fading or a full antenna elevation pattern is needed; the
  flat-fading Rician draw and the azimuth-only lobe become the special cases.
- Mesh or multi-hop routing lands, which is the BL-056 delay-tolerant-networking
  layer, not the per-link budget.
