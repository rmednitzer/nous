# ADR 0083: a load_w channel on the power estimator

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0080, ADR 0082

## Context

ADR 0082 made net-load propagation the endurance default and capped the
near-balance band conservatively at the deterministic point. Its first revisit
trigger named the next step: "a unified `load_w` estimator lands, tightening the
net-load posterior enough that the near-balance band is SoC-responsive." Until
now the self-model derived the load side of `net_w` from two stand-ins: the load
point from `power.truth()["load_w"]` (ground truth, which the self-model should
not peek at) and the load uncertainty from `compute_est.covariance["draw_w"]`
(the compute draw, a proxy for total load that is also mis-attributed). SoC,
thermal, and capacity all reason from estimator beliefs; only endurance's load
term reached around the estimators to ground truth.

The power subsystem already tracks `load_w` (the total electrical load the
battery sees, which the engine sets each tick from the committed compute draw),
but it was not in `sensor_obs`, so no estimator carried a belief about it.

## Decision

Add a `load_w` scalar channel to `PowerEstimator` (load is what the battery
sees, so it is a power-domain quantity), have `PowerSubsystem.sensor_obs` emit
`load_w` with a small observation noise, and switch the self-model endurance to
read the load belief (`power_est.point["load_w"]` and
`covariance["load_w"]`) instead of ground truth and the compute-draw proxy.

The load channel is tuned to reflect that `load_w` is a well-known engine input,
not a hidden state being inferred: a small observation noise (0.25 W) and modest
process noise let it converge tightly. This is honest, the current load really
is known, and the residual uncertainty is sensor noise plus how fast the load
can move between ticks. The endurance net-load sampling now draws the load from
this tight posterior and the charge from the APU posterior as before; the
endurance drivers narrow from `["power", "compute", "apu"]` to
`["power", "apu"]`, since load is now a power-estimator channel.

The change is additive: a new key in the `Estimate` dicts (no `base.py` Protocol
change, ADR 0007), the engine wiring unchanged because the channel defaults
cover construction and reload, and the conservative cap from ADR 0082 retained.

## Consequences

Measured on the reference profile after convergence: the load posterior is about
2.4 times tighter than the compute-draw proxy it replaces (sigma 0.12 W versus
0.30 W), and the SC-1 band-width margin (how much growing the SoC posterior
widens the endurance band) rises from roughly 2 percent to roughly 155 percent.
That is the ADR 0082 payoff: with the load side tight, the near-balance endurance
band is genuinely SoC-responsive rather than dominated by load uncertainty, so a
controller reads the SoC uncertainty it should act on. Endurance now reasons from
the same belief surface as every other capability, no longer peeking at ground
truth.

The honest limit: in the current single-consumer model the engine sets
`load_w` equal to the compute draw, so the channel filters the same underlying
signal `compute_est.draw_w` did. The gains here are the proper attribution, the
tight tuning a known input justifies, and reasoning from a belief rather than
truth, not new information. The real generalisation arrives when other consumers
are modelled and `load_w` is no longer a single subsystem's draw; the channel is
the seam that captures the total then. The conservative cap stays: relaxing it
(letting the SoC upside show above the point) is now more viable since the band
is SoC-responsive, but it remains a separate safety decision, and the APU charge
posterior is still a near-balance contributor, so it is not done here.

## Alternatives considered and rejected

- A separate `LoadEstimator` beside the others. Rejected: load is what the
  battery sees, a power-domain quantity, so the power estimator is its natural
  home; a new estimator adds a construction and wiring surface for no gain.
- Keep the compute-draw proxy. Rejected: it mis-attributes load to compute, is
  looser than a known input deserves, and leaves endurance reading ground truth
  for the load point, the exact false-belief-versus-truth gap this closes.
- Relax the ADR 0082 cap in the same change. Rejected: the cap is a separate
  safety decision, the charge side is still a near-balance contributor, and the
  honest-upside question is unresolved; keep the scope to the estimator.

## Revisit triggers

- Other load consumers are modelled, so `load_w` exceeds the compute draw and the
  unified channel captures a genuinely different total.
- The conservative cap is revisited now that the band is SoC-responsive (then the
  APU charge side likely needs a tighter belief first).
- The load channel's tuning proves mis-scaled for a platform whose load moves
  much faster than the reference (then lift the process noise to a profile knob).
