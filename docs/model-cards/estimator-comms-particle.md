# Model card: Comms particle filter

**Module:** `src/nous/estimators/comms.py`

**Backlog:** BL-030 (done as of 2026-05-26)

## Inputs

- Per-link RSSI, throughput, and packet-loss samples from
  `CommsSubsystem.sensor_obs()`.
- Subsystem-provided `connected` flag (treated as a weak observation
  channel; the filter does not blindly trust it when throughput
  evidence disagrees).

## Outputs

`Estimate` with `point = {connected_links, total_links, connected_links_belief}`.
The aggregate `connected_links` is the integer count of links whose
posterior belief crosses 0.5 and whose throughput exceeds the live
floor; `connected_links_belief` is the soft sum of per-link beliefs.
Per-link `LinkBelief` instances expose `belief()` (weighted mean over
the ensemble) and `variance()`.

## Filter structure

Per-link Sequential Importance Resampling (SIR) particle filter:

* **Particle representation:** N binary particles per link
  (default N=64). Each particle is `1` (connected) or `0` (disconnected)
  with a non-uniform weight.
* **Bootstrap:** new links start with half their particles connected
  and half disconnected so the first observation can resolve the
  hypothesis honestly.
* **Transition model (predict):** a sticky Markov chain. Base stay
  probabilities are `0.97` (connected -> connected) and `0.93`
  (disconnected -> disconnected). Channel quality (RSSI + packet loss)
  modulates the stay probabilities so a deteriorating link's particles
  flip toward disconnected faster than a steady one.
* **Observation model (update):** likelihood of the observation given
  each hidden state. The connected hypothesis is favoured by throughput
  near the expected envelope (Gaussian on log-throughput residual,
  sigma = 25% of expected). The disconnected hypothesis is favoured by
  zero-throughput observations and high packet loss. The `connected`
  flag from the subsystem nudges both likelihoods but does not
  dominate.
* **Resampling:** systematic resampling triggered when the effective
  sample size drops below `N/2`. Deterministic given the engine seed.

## SLA

- Update latency: under 5 ms with 64 particles per link.
- Covariance bound: `Var(belief) <= 0.25` after five consistent
  observations (i.e. sigma <= 0.5 over the binary connected /
  disconnected belief).
- Determinism: identical seeds produce identical particle trajectories
  (asserted by `tests/unit/test_comms_estimator.py::test_deterministic_under_seed`).

## Known failure modes

- Without a propagation model (`LIMITATIONS.md` L7) the filter cannot
  anticipate terrain-driven blackouts; the particles only react after
  RSSI degrades. BL-048 (propagation-aware comms model) is the right
  place to fix this.
- Bursty fading destabilises the belief; resampling helps but does not
  rescue a link whose RSSI bounces near the threshold every tick.
- The particle count is fixed at construction; very high link counts
  (>64 simultaneously) may need a smaller per-link N to stay inside
  the latency SLA.
