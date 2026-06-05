# Model card: Self-model (capability assessment)

**Module:** `src/nous/self_model/` (`assess.py`, `viability.py`, `explain.py`)

**Backlog:** BL-018, BL-035, BL-050

## Inputs

- Live estimator state from the engine: the power SoC Kalman, the thermal
  Kalman, and the compute Kalman (each point estimate plus its per-channel
  variance), with the relevant profile constants (`battery_wh`, the junction
  throttle threshold, the profile token rate). Each capability draws on one
  estimator's posterior. Passing `engine=None` returns a zero-filled
  assessment (the v0.1 stub contract).

## Outputs

Three `Capability` claims, each with a point value, a calibrated
`p5 / p50 / p95` band, a `confidence` in [0, 1], and a `drivers` list:

- `endurance_min` -- minutes the pack sustains the current net load
  (`load_w - charge_accepted_w`), from the SoC posterior and `battery_wh`.
- `thermal_headroom_c` -- degrees to the junction throttle threshold, from
  the junction-temperature posterior.
- `inference_capacity_tok_per_s` -- the profile token rate derated by the
  compute headroom left after thermal throttling, from the load posterior.

The bands come from a Monte Carlo over the estimator posterior (512 samples,
seeded, the default `mode="monte_carlo"`), which is honest under the non-linear
capability functions (endurance divides by net load, headroom subtracts from a
threshold); a `mode="gaussian"` linear approximation is retained as an opt-out.
`viability` answers a feasibility question by checking a requirement against
the conservative `p5` edge of the relevant band; `explain` renders the claims
with a limiting-driver line.

## SLA

- Latency: the Monte Carlo (512 samples over three capabilities) stays well
  under the per-tick budget; sub-millisecond per capability.
- The `p50` is the deterministic point estimate; `p5` and `p95` are clamped to
  bracket it, so the band always contains the point.

## Known failure modes

- The claims are only as trustworthy as the estimators beneath them (see the
  power SoC, thermal, and compute estimator cards). A diverged estimator
  yields a confident-looking but wrong claim; `confidence` reflects only the
  reported variance, not estimator bias.
- Each band propagates a single source of uncertainty (SoC for endurance,
  junction temperature for headroom, load for capacity) and treats the other
  terms (net load, the throttle threshold, the profile token rate) as
  deterministic, so the bands understate total uncertainty.
- `endurance_min` under net charging is unbounded; it returns a 24 h sentinel
  with `confidence=0`, a hint rather than a bound.
- `inference_capacity_tok_per_s` is a derate of the profile's
  `compute.inference_local.tok_per_s_p50`, a published-benchmark estimate (the
  local model is the BL-043 mock), not a measured rate on this device.
