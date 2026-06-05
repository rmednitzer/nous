# Model card: Compute subsystem

**Module:** `src/nous/subsystems/compute.py`

**Backlog:** BL-007

## Scope

Turns a controller-supplied load fraction (0..100 %) into an electrical draw
through the profile's piecewise-linear `compute.load_curve` (with
`draw_w_idle` / `draw_w_load` as the endpoints when the curve is absent). The
engine reads `draw_w` each tick and feeds it into both the power subsystem
(electrical load) and the thermal subsystem (junction dissipation), so a
"spin up inference" command propagates through battery endurance, junction
temperature, and the FSM safety context together.

Delivered load is the minimum of the controller's request and every active
ceiling: the thermal-throttle ceiling (the engine reports junction
throttling, capping delivered load to mimic DVFS) and the ADR 0029 FSM
mode-load ceiling (entering `SAFE` / `LOW_POWER` / `THERMAL_LIMIT` caps load).
The request is preserved under the cap so it lifts on recovery.

## Inputs

| Seam | Notes |
|------|-------|
| `set_load_pct` | Direct fractional steer (scenario YAML) |
| `set_inference_rate` | Token-per-second request, via `inference_local.tok_per_s_p50` |
| `set_thermal_throttle` | Engine reports junction throttling, clips delivered load |
| `set_mode_load_ceiling` | FSM posture entry action (ADR 0029) |

## State (truth())

| Field | Units | Notes |
|-------|-------|-------|
| `load_pct` | % | Delivered load (after every ceiling) |
| `requested_load_pct` | % | Controller request, preserved under the cap |
| `draw_w` | W | Interpolated from the load curve at `load_pct` |
| `throttled` | bool | Delivered load clipped below the request |
| `mode_load_ceiling_pct` | % or None | Active FSM posture ceiling |

## Outputs (sensor_obs())

| Field | Units | Sigma |
|-------|-------|-------|
| `load_pct` | % | 1.5 |
| `draw_w` | W | 0.5 |

## Profile fields

```yaml
compute:
  draw_w_idle: 8
  draw_w_load: 60
  load_curve:                     # piecewise-linear (load_pct -> draw_w)
    - { load_pct: 0,   draw_w: 8 }
    - { load_pct: 100, draw_w: 60 }
  inference_local:
    tok_per_s_p50: 200            # 100%-load token-rate reference
    energy_j_per_tok: 0.12
```

## Known limitations

- The load curve and the inference figures are profile estimates
  (order-of-magnitude, consistent with published Jetson benchmarks), not
  measured on a real device; the real local model is BL-043.
- Thermal throttling is a single fixed ceiling (60 %), not a DVFS
  frequency/voltage curve.
- Load is one scalar fraction. There is no per-core, per-accelerator, or
  workload-heterogeneity model; a mixed CPU/GPU workload is a single number.
- The channel coupling between load and draw is not exploited by the estimator
  (independent-channel Kalman; full EKF is BL-031a).
