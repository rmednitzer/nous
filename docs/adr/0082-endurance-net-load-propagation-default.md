# ADR 0082: net-load propagation is the endurance default

- **Status:** Accepted
- **Date:** 2026-06-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0080
- **Amends:** ADR 0080 (the net-load-propagation opt-in default)

## Context

ADR 0080 made each capability band propagate every uncertain input, but left one
piece opt-in: endurance's net-load propagation (the APU-charge posterior and the
compute-draw posterior fed through `net_w = load_w - charge_accepted_w`). The
stated reason was that endurance divides by net load, so near energy balance the
`1/net_w` term is heavy-tailed and the upper quantile saturates, which would break
the SC-1 safety property (growing SoC posterior covariance must widen the band, so
the controller cannot act on false precision, loss L-1).

That caution was calibrated against a buggy intermediate during 0080's
development, where the per-sample endurance was clipped to the net-charge sentinel
(24 h) even when the deterministic point exceeded it, collapsing the whole band to
a single saturated interval. The shipped 0080 code fixed the clip (the sentinel is
`max(point_min, cap)`), but the opt-in default was kept out of caution and never
re-measured against the corrected code.

Re-measuring it against the shipped code changes the picture. With the corrected
sentinel, flipping the default on and running the suite breaks only the two tests
that hard-coded the old opt-off drivers; SC-1's band-width and confidence
monotonicity both still hold (at the reference idle point the loose band is wider
than the tight one, and confidence still falls with SoC sigma), as do the `p5 >= 0`
floor, the point mode-invariance, and the seeded determinism. The opt-in was
unnecessary.

## Decision

Make net-load propagation the endurance default (`propagate_net_load` defaults to
true), so an unconfigured twin reflects net-load uncertainty in the endurance band
instead of treating net load as exact. Disable it per profile with
`self_model.priors.propagate_net_load: false` to recover the SoC-and-battery-only
band.

The near-balance heavy tail is handled by the existing sentinel: a net-charging
draw, and any net-positive draw whose endurance would exceed the point, are capped
at the deterministic point estimate. That keeps the band honestly wide on the
downside (the net-load uncertainty shows up as a lower `p5`) while bounding the
upper tail conservatively. The cost is a deliberate understatement of the
net-charging upside near balance (the band's `p95` sits at the point rather than
reaching toward "unbounded"), which is the safe direction for a "can I sustain
this?" decision: the controller is told it has at least the lower edge, never
falsely promised more.

The flag's coercion keeps the same safe bias. A real boolean is honoured (`false`
disables); any non-bool value (for example a quoted `"false"`) is junk and falls
back to the default (on), so a configuration typo widens the band rather than
silently disabling propagation. The two tests that encoded the opt-off default are
rewritten: SC-1 is unchanged and still passes, the propagation test now asserts the
on-by-default drivers and that disabling narrows the band, and the coercion test
asserts a real `false` disables while a non-bool falls back to on.

## Consequences

The endurance band is honest about net-load uncertainty by default, closing the
part of the 0080 model-card note that net load was still treated as exact unless an
operator opted in. Under inference load (net comfortably positive) this is a clean
widening from the charge and draw posteriors; at idle (near balance) the band is
wide and conservatively upper-bounded at the point. The endurance drivers now read
`["power", "compute", "apu"]` by default, so `explain` and `situation` name the
subsystems the claim actually depends on.

The cost is the documented upside understatement near balance, and that endurance
is now a 512-sample Monte Carlo over four inputs by default rather than two (still
well under the per-tick budget). SC-1 continues to hold but, near balance, by a
smaller margin than when net load was treated as exact, because the band there is
genuinely dominated by net-load uncertainty rather than SoC; that is the honest
behaviour, and the loss SC-1 guards (acting on false precision) is better
prevented by the wider band, not worse.

## Alternatives considered and rejected

- Keep it opt-in (ADR 0080). Rejected: the opt-in rested on a saturation that the
  shipped sentinel already prevents, so the default was understating uncertainty
  for no safety gain.
- Build a unified load estimator first (0080's revisit trigger). Rejected as a
  prerequisite: the corrected sentinel already preserves SC-1, so the default flip
  does not need it; a tighter load posterior remains a worthwhile future refinement
  but is not load-bearing for this decision.
- Represent the net-charging upside honestly (let `p95` exceed the point near
  balance). Rejected for now: an unbounded-leaning upper tail reintroduces the
  saturation question and is the unsafe direction for a sustainment decision; the
  conservative cap is the safer default. Revisit if a controller needs the upside.

## Revisit triggers

- A unified `load_w` estimator lands, tightening the net-load posterior enough that
  the near-balance band is SoC-responsive without the conservative cap.
- A controller needs the honest net-charging upside (then model the upper tail
  explicitly and re-test SC-1 against it).
- The near-balance SC-1 margin proves fragile under a future change (then isolate
  the SoC channel in the SC-1 test by disabling propagation there).
