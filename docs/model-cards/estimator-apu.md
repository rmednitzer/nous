# Model card: APU estimator

**Module:** `src/nous/estimators/apu.py`

**Backlog:** BL-005a

## Inputs

Sensor observations from ``ApuSubsystem.sensor_obs()``. Each
observation carries the five source channels plus the total, with a
calibrated standard deviation per channel.

## Outputs

``Estimate`` with ``point = {solar_w, fuelcell_w, vehicle_w, usbc_w,
hand_crank_w, total_w}`` and per-channel scalar covariances.

## Algorithm

A 1-D Kalman filter per channel. ``predict(dt)`` grows the variance by
``process_sigma_per_s**2 * dt``. ``update(obs)`` applies the standard
scalar Kalman gain ``K = P / (P + R)``; ``R`` is taken from the
observation's noise dict per channel.

## SLA

- Update latency: under 1 ms per call.
- Steady-state sigma per channel: under 2 W after roughly 20 ticks of
  consistent observation.

## Known failure modes

- A source that toggles on/off rapidly within one tick will be
  smoothed; the estimator does not model discrete state. For a
  scenario that needs sub-tick transients, the controller should
  read ``ApuSubsystem.truth()`` directly.
- Cross-channel correlations are ignored. The estimator does not
  enforce ``total_w = sum(per-source)``; the sensor observation
  encodes the equality and a divergence indicates either a sensor
  fault or a subsystem bug.
