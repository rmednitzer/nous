---
name: nous-self-model
description: Read and interpret the self-model capability claims.
---

# Self-model

The self-model layer aggregates estimator state into capability claims
with calibrated quantiles. Call `self_model_assess` with a question
(or no question for the default summary).

## Fields

- `endurance` -- minutes of operating life at the current load.
- `thermal_headroom` -- degrees Celsius below the throttle threshold.
- `inference_capacity` -- tokens per second sustainable on the local
  path.
- `extra` -- additional capability claims relevant to the question.

Each claim carries `p5 / p50 / p95` and a `confidence` value. A low
confidence means the estimator has diverged; treat the central
estimate as suspect and either widen the operating envelope or wait
for the next update.

## Why a quantile and not a point estimate

The point answers "what is the best guess"; the p5/p95 answer "how
likely is the answer to be wrong by more than this". When the p5 falls
below an operational threshold, escalate.
