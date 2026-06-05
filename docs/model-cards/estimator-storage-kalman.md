# Model card: Storage Kalman

**Module:** `src/nous/estimators/storage.py`

**Backlog:** BL-008, BL-050

## Inputs

- Used-space and NAND-wear samples from `StorageSubsystem.sensor_obs()`.
  The subsystem advertises a per-channel observation sigma; the estimator
  falls back to `0.05 GiB` on used space and `0.1 %` on wear when one is
  absent. `predict` inflates each channel's variance very slowly
  (`0.001 GiB^2/s` on used, `0.0001 %^2/s` on wear), matching the slow
  physical drift of both quantities, so a gap between updates barely grows
  the covariance.

## Outputs

`Estimate` with `point = {used_gib, wear_pct}` and a matching two-entry
diagonal covariance (one variance per channel, no cross-covariance). The two
channels are filtered as independent scalars.

## SLA

- Update latency: under 1 ms per call.
- Covariance bound: with the slow process variance the per-channel sigma
  converges to roughly the observation floor (~0.05 GiB used, ~0.1 % wear)
  once updates are flowing, and decays gracefully toward the prior when they
  are not.

## Known failure modes

- Used space and wear are physically coupled (every write advances both
  through the subsystem's write-amplification model), but the filter treats
  them as independent channels and does not cross-check one against the
  other.
- The filter does not enforce monotonicity. Real NAND wear only increases,
  but a noisy observation can fold the wear estimate slightly downward; a
  consumer that needs a monotone wear series should read the subsystem truth
  (`wear_pct`), which is monotone by construction.
- The estimate tracks observed used space and wear; it does not project
  future wear or remaining endurance. Those are subsystem-model reads, not
  filter state.
