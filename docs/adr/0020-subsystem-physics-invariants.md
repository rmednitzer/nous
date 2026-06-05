# ADR 0020: Property-based invariants for subsystem physics

- **Status:** Accepted
- **Date:** 2026-05-24
- **Authors:** rmednitzer
- **Builds on:** ADR 0013, ADR 0019

## Context

`tests/unit/test_estimator_properties.py` covers the filter contract
with Hypothesis: covariance monotonicity under `predict`, posterior
shrink under `update`, NaN rejection. The subsystem layer underneath
has no equivalent. Peukert capacity, the lumped thermal model, the
link-budget envelope, and the FSM admit transitions all carry
closed-form invariants that the test suite asserts only through
hand-picked numeric examples (`tests/unit/test_power_subsystem.py` and
peers).

The C5 finding in `AUDIT.md` ("stub estimators advertise covariance
they never compute") is exactly the failure mode property-based
testing catches: a stub satisfies its example tests because the
examples were chosen to match the stub's output, and the absence of an
invariant lets the silent regression survive. The regression-test file
landed in `tests/regression/test_audit_findings.py` pins the *fixed*
behaviour; this ADR is about catching the *next* such defect before it
gets a finding id.

The shape of the test is closed-form facts about the modelled physics,
not numeric examples. An RK4 integrator is checked against
`dx/dt = x -> e^t` at tight tolerance; gravity recovers the
inverse-square law at large `r`; an atmosphere model satisfies
`rho = P / (R * T)`; energy is conserved across a full orbit. A
regression that breaks the invariant fails on every seed, not only
on the seed that produced the example test.

The deterministic seed seam in ADR-0019 is a prerequisite. Without it,
Hypothesis cannot shrink to a failing seed, and a flaky property test
becomes a noise generator that contributors mute rather than fix.

## Decision

Add `tests/unit/test_subsystem_invariants.py` (one file, parameterised
across subsystems) that asserts the following invariants under
Hypothesis with the engine RNG injected per case:

- **Power (Peukert).** Available capacity is monotonically
  non-increasing in discharge current at constant temperature.
- **Thermal (lumped two-mass).** With load=0 and ambient held
  constant, both temperatures converge monotonically to ambient.
  With load>0, junction temperature is strictly above enclosure
  temperature once steady state is approached.
- **Compute.** ``draw_w`` is monotonic in ``load_pct`` at constant
  throttle state. Throttling never increases draw or load.
- **Comms link envelope.** Throughput is monotonic in SNR
  (loss-monotone in the reverse direction). Link age is monotonic in
  ticks-since-last-tx.
- **Position.** Under predict-only (fix lost), the Kalman covariance is
  monotone non-decreasing in elapsed time. Under observation, the
  posterior covariance is monotone non-increasing.
- **Storage.** ``used_gib`` is monotone non-decreasing under writes
  (no negative writes). ``wear_pct`` is monotone non-decreasing.
- **FSM.** ``transition`` is never a no-op that lies: the returned
  mode equals the FSM's current mode after the call. An unguarded
  trigger that succeeds always advances `history`. (Adds Hypothesis
  coverage to the existing example tests in
  `tests/unit/test_state_machine_guards.py`.)

Each invariant lives next to a docstring stating the physical or
contractual basis. A failure prints the shrunk input. Tolerances are
named constants in the test module (`_THERMAL_STEADY_STATE_REL_TOL`
etc.) so a relaxed tolerance is reviewable in diff.

The "regression test for each prior defect" pattern stays in
`tests/regression/`; property invariants belong with the unit suite.
A future open-source contribution that proposes a new subsystem must
ship the invariant section with the implementation (extension to
`CONTRIBUTING.md` lands with this ADR's implementation).

## Consequences

Easier: silent stub-pretending-to-be-real defects surface as
shrunken counter-examples. The invariants double as engineering
documentation: a reader scanning the test file sees the physical
contract of each subsystem at a glance. Tolerances and bounds become
reviewable.

Harder: a subsystem rewrite that violates an invariant fails the
suite, and the contributor must decide whether the invariant was
wrong or the new model is. The Hypothesis shrinking budget for the
full subsystem matrix is non-trivial; the test file is allowed up to
ten seconds of CPU in CI without further justification.

Alternatives rejected:

- **Example-based tests only.** The C5 defect proved these are not
  enough; an invariant that holds across all inputs is what catches
  a stub.
- **Hypothesis on the engine integration boundary.** Possible, but
  the failure messages become too far from the subsystem to be
  diagnostic; the per-subsystem level is where the invariant is
  legible.

## Revisit triggers

- A subsystem grows enough state that 1-D invariants are no longer
  the cheapest abstraction; the file may need to split per subsystem.
- Hypothesis CI cost crosses ten seconds for the full file; revisit
  the per-strategy `max_examples` and the `deadline` config.
- A regulatory body requires evidence of physics-correctness for
  certification; the invariants may need to be lifted to a formal
  proof obligation under `docs/stpa/`.
