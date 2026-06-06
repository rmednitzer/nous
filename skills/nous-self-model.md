---
name: nous-self-model
description: Read and interpret the self-model capability claims.
---

# Self-model

The self-model layer aggregates estimator state into capability claims
with calibrated quantiles. Call `self_model_assess` with a question
(or no question for the default summary).

> `self_model_assess` is wired (BL-018). It returns one claim per
> capability today, each carrying a `point`, calibrated `p5`/`p50`/`p95`
> quantiles (Monte Carlo over the estimator posteriors by default, BL-035),
> a `confidence`, and the `drivers`, plus an `explanation` string. Read the
> quantiles: a `confidence` near 0 or a collapsed band means low
> information, not absence.

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

## The fused situational read

`self_model_situation` (T0, BL-061) is the one-call tactical picture. It
reuses the same capability claims (so the headline numbers match
`self_model_assess`) and layers on what a controller would otherwise stitch
together by hand:

- `posture` -- the FSM `mode` plus the operator and comms labels with their
  reasons, and a one-word `summary` (`nominal` / `degraded` / `safed` /
  `terminal` / `standby`).
- `capabilities` -- each claim with a `status` (`nominal` / `watch` /
  `degraded` / `critical`) and a `provenance` list: the backing estimator's
  `source` and its `age_s` (staleness). `age_s` is the estimator clock lag; it
  sits near zero under live ticking and grows when an estimator stalls. The
  live trust signal is still `confidence`, so read both: a fresh-but-uncertain
  claim and a stale claim are different problems.
- `safety` -- the runtime enforcer's cumulative violation posture.
- `recommendations` -- a short ranked list of degraded-mode advice, ordered
  the way the device auto-safes (operator, then power, then thermal, then
  comms, then navigation and inference). These are advisory: the safety
  enforcer, not this list, is what actually refuses or clamps an action.

Reach for `self_model_situation` when you want the whole picture in one read;
reach for `self_model_assess` when you only need the capability numbers, and
`self_estimator_status` when you need the raw estimator covariances.
