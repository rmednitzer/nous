# ADR 0080: honest multi-source capability quantiles

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0038, ADR 0079 (BL-035)

## Context

The self-model's Monte Carlo quantile mapping (BL-035) draws samples from an
estimator posterior, pushes them through a capability function, and reports the
empirical 5 / 50 / 95 band. Each capability sampled exactly one source: SoC for
endurance, junction temperature for headroom, load for inference capacity. The
other inputs were read as exact, single deterministic values: the net load and
`battery_wh` for endurance, the throttle threshold for headroom, the benchmark
token rate for capacity. The model card recorded this as a known failure mode,
the bands "understate total uncertainty", and it is the kind of false precision
DR-1 exists to prevent: a controller that reads a tight band trusts a number the
model has no right to be tight about.

The honest fix is to propagate every uncertain input a capability depends on,
not one. The inputs split into two kinds. Some have a real posterior the engine
already computes but the self-model ignored: the APU charge (the APU output
estimator's `total_w`) and the compute draw (the compute Kalman's `draw_w`),
which together set endurance's net load. The rest are spec constants with no
estimator at all: `battery_wh`, the throttle threshold, the benchmark token
rate. These are not beliefs the device filters, they are datasheet, benchmark,
and manufacturing figures, each with a tolerance the model was pretending was
zero.

## Decision

Generalise each capability's Monte Carlo to sample all its uncertain inputs from
the shared seeded RNG (the estimators carry no cross-covariance, so the draws are
independent marginals), keeping the headline `point` a deterministic computation
outside the branch so it stays mode-invariant.

For the spec constants, introduce a small profile-configurable design prior under
`self_model.priors`, sampled in the Monte Carlo path: `battery_wh_cv` (default
0.03) for the pack capacity, `junction_throttle_sigma_c` (default 1.5 C) for the
throttle threshold, and `tok_per_s_cv` (default 0.10) for the benchmark token
rate. These are priors, not posteriors: the spreads stand for spec tolerance, are
documented as such, and a value of 0 recovers the v0.1 band. The defaults are on,
so the bands are honestly wider by default. The reader is attacker-influenceable
profile content, so every field is coerced and a non-finite or negative value
falls back to its default rather than poisoning a band.

For endurance's net load, the APU-charge and compute-draw posteriors are
available behind an opt-in flag, `self_model.priors.propagate_net_load`, off by
default. Endurance divides by net load, so near energy balance the `1/net_w` term
is heavy-tailed: a draw that crosses into net charging reads as the net-charge
sentinel and the explosive upper tail saturates there. That is honest, but a
saturated upper quantile no longer widens monotonically with SoC uncertainty
(the DR-1 property the SC-1 test pins), and at idle the reference device sits
near balance. Rather than weaken that safety monotonicity in the default path,
the net-load propagation is opt-in for the regimes where net load is comfortably
positive (under inference load), while the clean spec-constant priors carry the
default honesty gain. The Gaussian fallback stays the single-source linear
approximation it always was, the documented v0.1 opt-out.

This is additive and read-side only: no estimator, no subsystem, and no MCP tool
changes, so there is no `policy.py` change. The capabilities still flow through
`assess`, `explain`, `situation`, and `viability` unchanged in shape.

## Consequences

A controller now reads bands that reflect total uncertainty rather than one
source. The thermal headroom band widens to admit the throttle threshold's
tolerance, the inference capacity band the benchmark rate's, and the endurance
band the pack capacity's, all by default and all traceable to a named prior the
operator can tune or zero out. Where an operator wants the fuller endurance
propagation and runs with net load comfortably positive, the opt-in adds the
APU-charge and compute-draw posteriors and the endurance drivers grow from
`["power"]` to `["power", "compute", "apu"]` to say so.

The cost is honesty about the priors themselves: a band is now only as
trustworthy as the spec tolerance behind it, and the defaults (3 percent on
capacity, 1.5 C on the throttle, 10 percent on the token rate) are reference
figures, not measured tolerances for a specific unit. The net-load saturation is
a real limit, documented on the opt-in, not hidden. `confidence` remains the
dominant-estimator heuristic it was; the bands, not the scalar, carry the new
information.

## Alternatives considered and rejected

- Propagate net load by default. Rejected: the `1/net_w` saturation breaks the
  SC-1 monotonicity (SoC uncertainty must widen the band) at the reference
  device's idle operating point, trading a safety property for honesty in a
  regime where the endurance figure is already a capped hint.
- Treat the spec constants as exact and propagate only the available posteriors.
  Rejected: it leaves the headroom and capacity bands single-source, the exact
  failure mode this ADR closes, and those two have no posterior to propagate.
- Fold the prior spreads into `confidence` instead of the bands. Rejected: the
  band is where a controller reads uncertainty for a decision; a scalar that
  drops without the band widening is the false precision restated.
- A joint covariance across estimators. Rejected: the estimators are independent
  scalar filters with no cross-covariance to exploit, so independent marginal
  draws are both correct and the only thing the infrastructure supports.

## Revisit triggers

- A unified load estimator lands (the compute draw is only the variable part of
  total load today), at which point net-load propagation could become the
  default without the saturation caveat.
- The design-prior defaults prove mis-scaled for a very different platform (then
  the profile override is the seam, already in place).
- A controller needs `confidence` to reflect the prior spreads, not just the
  dominant estimator (then derive it from the relative band width).
