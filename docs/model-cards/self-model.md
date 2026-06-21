# Model card: Self-model (capability assessment)

**Module:** `src/nous/self_model/` (`assess.py`, `viability.py`, `explain.py`)

**Backlog:** BL-018, BL-035, BL-055

## Inputs

- Live estimator state from the engine: the power SoC Kalman, the thermal
  Kalman, the compute Kalman, the APU output estimator, and the EO/IR
  detection-range Kalman (each point estimate plus its per-channel variance),
  with the relevant profile constants (`battery_wh`, the junction throttle
  threshold, the profile token rate) carried as small design priors. A
  capability propagates every uncertain input that feeds it, not a single
  source (ADR 0080). Passing `engine=None` returns a zero-filled assessment
  (the v0.1 stub contract).

## Outputs

Four `Capability` claims, each with a point value, a calibrated
`p5 / p50 / p95` band, a `confidence` in [0, 1], and a `drivers` list:

- `endurance_min` -- minutes the pack sustains the current net load
  (`load_w - charge_accepted_w`), from the SoC posterior and `battery_wh`.
- `thermal_headroom_c` -- degrees to the junction throttle threshold, from
  the junction-temperature posterior.
- `inference_capacity_tok_per_s` -- the profile token rate derated by the
  compute headroom left after thermal throttling, from the load posterior.
- `perception_range_m` -- the best-band EO/IR detection range
  (`max(eo, ir)`), from the EO/IR posterior over both bands (BL-055, ADR 0079).
  The Monte Carlo branch takes the per-sample maximum so the band reflects the
  nonlinear best-of-two.

The bands come from a Monte Carlo over every uncertain input a capability
depends on (512 samples, seeded, the default `mode="monte_carlo"`): the
estimator posteriors that feed it plus a small profile-configurable design
prior for each spec constant that has no estimator (ADR 0080). It is honest
under the non-linear capability functions (endurance divides by net load,
headroom subtracts from a threshold); a `mode="gaussian"` single-source linear
approximation is retained as an opt-out.
`viability` answers a feasibility question by checking a requirement against
the conservative `p5` edge of the relevant band; `explain` renders the claims
with a limiting-driver line.

## SLA

- Latency: the Monte Carlo (512 samples over three capabilities) stays well
  under the per-tick budget; sub-millisecond per capability.
- The `p50` is the empirical sample median in Monte Carlo mode and the
  deterministic point in Gaussian mode; `p5` and `p95` are clamped to bracket
  the point, so the band always contains it.

## Known failure modes

- The claims are only as trustworthy as the estimators beneath them (see the
  power SoC, thermal, and compute estimator cards). A diverged estimator
  yields a confident-looking but wrong claim; `confidence` reflects only the
  reported variance, not estimator bias.
- The spec constants (`battery_wh`, the throttle threshold, the benchmark token
  rate) carry design priors, not estimator posteriors: the prior spreads are
  datasheet/benchmark tolerances configured under `self_model.priors`, so a band
  is only as honest as those priors. Endurance can also propagate the net-load
  posteriors (APU charge, compute draw) behind the opt-in
  `self_model.priors.propagate_net_load`, off by default because the `1/net_w`
  term saturates the upper quantile near energy balance.
- `endurance_min` under net charging is unbounded; it returns a 24 h sentinel
  with `confidence=0`, a hint rather than a bound.
- `inference_capacity_tok_per_s` is a derate of the profile's
  `compute.inference_local.tok_per_s_p50`, a published-benchmark estimate (the
  local model is the BL-043 mock), not a measured rate on this device.
- `perception_range_m` reports only the best of the two bands as one number; a
  controller that needs per-band reach or the target-specific line-of-sight
  verdict reads `eoir_status`. Its advisory status floors are heuristics tuned to
  the reference profile, like the other capabilities' floors.
