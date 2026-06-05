# Model card: Compute Kalman

**Module:** `src/nous/estimators/compute.py`

**Backlog:** BL-031a, BL-050

## Inputs

- Delivered load fraction and electrical draw samples from
  `ComputeSubsystem.sensor_obs()` (`load_pct_sigma = 1.5 %`,
  `draw_w_sigma = 0.5 W`). The observation reports the *delivered* load,
  after thermal throttling and the ADR 0029 mode-load ceiling clip it, not
  the controller's requested load. `predict` inflates each channel's
  variance with elapsed time (`0.5 %^2/s` on load, `0.1 W^2/s` on draw); it
  is not driven by the requested load or the profile load curve.

## Outputs

`Estimate` with `point = {load_pct, draw_w}` and a matching two-entry
diagonal covariance (one variance per channel, no cross-covariance). The two
channels are filtered as independent scalars: the filter does not exploit
that draw tracks load through the profile's piecewise-linear `load_curve`.
Coupling the channels through that curve (so a draw observation constrains
the load estimate and vice versa) is the full multi-state EKF deferred to
BL-031a.

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: at the default 2 Hz tick the load sigma converges toward
  the observation floor (~1.5 %) in steady state and the draw sigma toward
  ~0.5 W; a load step inflates both by the process variance until the next
  update folds the observation back in.

## Known failure modes

- The estimate follows *delivered* load, so when the FSM caps compute (mode
  ceiling) or thermal throttling clips it, the filter tracks the reduced
  value. A reader who wants the controller's requested load reads the
  subsystem truth (`requested_load_pct`), not this estimate.
- No load-curve prior: at a load fraction the device has not recently
  visited, the draw estimate is only as good as the latest observation;
  there is no model-based prediction of draw from load until BL-031a couples
  the channels.
- The independent-channel simplification means a single-channel sensor fault
  (a plausible draw with an implausible load, or the reverse) is not
  cross-checked; both channels are believed on their own observation noise.
