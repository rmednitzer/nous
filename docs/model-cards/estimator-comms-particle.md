# Model card: Comms particle filter

**Module:** `src/nous/estimators/comms.py`

**Backlog:** BL-030

## Inputs

- Per-link RSSI, throughput, and packet-loss samples from
  `CommsSubsystem.sensor_obs()`.

## Outputs

`Estimate` with `point` summarising connection state and loss; the
self-model maps this onto the `CommsState` vocabulary.

## SLA

- Update latency: under 5 ms with 64 particles (the default).
- Covariance bound: connection-state belief sigma <= 0.5 (over the
  binary connected/disconnected; closer to 0 means high confidence).

## Known failure modes

- Without a propagation model (`LIMITATIONS.md` L7) the filter cannot
  anticipate terrain-driven blackouts; the particles only react after
  RSSI degrades.
- Bursty fading destabilises the belief; the L3 propagation-aware
  follow-up (BL-048) is the right place to fix this rather than
  hardening the filter against signals it cannot see.
