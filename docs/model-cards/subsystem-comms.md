# Model card: Comms subsystem

**Module:** `src/nous/subsystems/comms.py`

**Backlog:** BL-012 (core), BL-048 / BL-088 (propagation), BL-077 (outbox),
BL-056 (DTN mesh), BL-060 (EMCON)

## Scope

Carries the per-link radio envelope for each configured comms link (LTE,
LoRa, TAK, ...) and accounts every transmission through a single `tx()`
seam. Each link advertises a bandwidth, a nominal RSSI, a packet loss, and
a freshness `max_age_s`; the live per-link state feeds the comms estimator
(a particle filter, separate card) and, through it, the FSM
`state.comms_state`. Because `tx()` is the one seam every emission passes
through, it is where the propagation link budget, the store-and-forward
triage, and the operator emission posture all attach.

## Inputs

| Seam | Notes |
|------|-------|
| `tx(link_id, n_bytes, *, now_s=)` | Account an emission; returns the bytes sent, `0` when capacity is zero, the link is down, or an EMCON posture denies or windows it |
| `set_link_state` / `inject_comms_loss` | Scenario overrides that hard-force a link state above the physics |
| `position_fn` | Lazy device position for the propagation slant range (ADR 0019 injection seam) |

## Per-link state (`truth()` / `sensor_obs()`)

| Field | Units | Notes |
|-------|-------|-------|
| `bandwidth_bps` | bit/s | Rated link bandwidth |
| `capacity_bps` | bit/s | Propagation-solved achievable rate (equals the bandwidth for a static link; `0` when the link is not live) |
| `rssi_dbm` | dBm | Live RSSI (the propagation link budget where a link configures one, else the nominal) |
| `loss_pct` | % | Live packet loss |
| `age_s` | s | Time since the last accounted traffic; the link ages out past `max_age_s`, tracked by `age_out_count` / `last_aged_out_at_s` |

## Layered behaviour

- **Propagation (BL-048 / BL-088, ADR 0053 / 0054).** A link with a
  `propagation` block solves RSSI, loss, and the SNR-derived
  `capacity_bps` each tick from a first-order link budget (path loss,
  knife-edge diffraction, kTB noise, antenna pattern, multipath) over the
  slant range from the device position.
- **Store-and-forward outbox (BL-077, ADR 0047).** A package a degraded or
  denied link cannot carry is held in a bounded, precedence-ordered outbox
  and drained in triage order as the link recovers.
- **DTN mesh (BL-056, ADRs 0061-0064).** Above the per-link envelope, a
  multi-node bundle mesh relays a bundle hop by hop with custody transfer,
  dedup, and replay; see the [DTN conformance posture](../conformance/dtn-bpv7.md).
- **EMCON (BL-060, ADRs 0065-0067).** An operator emission posture gates
  `tx()`: a named profile, a duty-cycle window, or metadata minimisation
  can deny, defer, or coarsen an emission, with a denied or closed-window
  send auto-triaged to the outbox.

## Profile fields

```yaml
comms:
  links:
    - id: lte
      bandwidth_bps: 20000000
      rssi_dbm_nominal: -75
      loss_pct_nominal: 0.5
      max_age_s: 30
  outbox: { enabled: true, max_packages: 256, max_bytes: 1048576, default_ttl_s: 300 }
  # optional, additive: a per-link `propagation` block, a `dtn` mesh
  # section, and an `emcon` posture section; each is inert when absent.
```

## Known limitations

- The per-link envelope is a scalar model: no per-packet queueing, jitter,
  or protocol overhead is represented.
- Inter-node DTN loss is a Bernoulli draw, not the propagation link budget
  the device's own links carry (`LIMITATIONS.md` L12).
- A forced override (`set_link_state` / `inject_comms_loss`) hard-overrides
  the propagation physics so a scenario can pin a link state directly.
