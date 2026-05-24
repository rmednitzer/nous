# ADR 0019: Deterministic seed and clock seam at the engine boundary

- **Status:** Accepted
- **Date:** 2026-05-24
- **Authors:** rmednitzer
- **Builds on:** ADR 0010, ADR 0013

## Context

The engine and its subsystems mix randomness and wall-clock time in
ways that are individually defensible but collectively make the
simulator non-reproducible. `Engine` reads `time.monotonic()` directly
(`src/nous/engine.py:126`). Subsystem `sensor_obs()` payloads already
declare per-channel sigmas (`PowerSubsystem.sensor_obs()` exposes
`soc_pct_sigma`, `voltage_v_sigma`, `current_a_sigma`; the apu,
thermal, comms, and storage subsystems do the same) so that the
estimator layer can weight observations. The next step is to actually
sample those sigmas at the subsystem boundary, and the moment that
happens the simulator needs a single RNG handle to draw from, or the
sampling will reach for the `numpy.random` global by default. `AUDIT.md`
M8 and M9 are adjacent: both ask for engine-tick coverage that a
deterministic seam makes cheap (a unit test can assert exact tick
trajectories without re-instantiating the engine in every Hypothesis
case, the way `tests/unit/test_estimator_properties.py` does today).

The shape that closes this gap is well established in simulator
practice: a single `np.random.default_rng(seed)` threaded through
every randomised component, and a Monte Carlo dispatcher that derives
per-run seeds as `base_seed + i` so runs do not poison each other's
globals. The same shape is missing here, and we feel its absence
wherever the test suite needs to assert "running the same scenario
twice produces the same trajectory."

The simulator's value proposition is legibility (`CLAUDE.md` "Repo
purpose"). A non-reproducible run is illegible: the controller cannot
tell whether a change in behaviour is a real shift in the device's
posture or a sampled noise difference. The deterministic seam is a
prerequisite for honest scenario regression testing, for Monte Carlo
dispersion, and for the conservation-law / physics invariants tracked
in ADR-0020.

## Decision

Add two constructor seams to `Engine`:

```python
class Engine:
    def __init__(
        self,
        *,
        seed: int | None = None,
        clock: Clock | None = None,
        ...
    ) -> None:
```

`seed` flows into a single `numpy.random.Generator` that the engine
hands to every subsystem and estimator at construction. Each
subsystem's existing scenario-control `set_*` helpers stay; once
observation sampling lands, the per-instance default RNG derives from
the engine handle rather than the numpy global. A seed of `None`
preserves today's behaviour by falling back to the OS entropy source,
so existing tests that do not care about determinism keep passing.

`clock` is a thin Protocol over `monotonic`, `wall`, and `sleep`. The
default is `MonotonicClock`, which is the current `time.monotonic()`
behaviour. A `VirtualClock(start_s)` lives in `nous/clocks.py` and
advances under explicit caller control; tests use it to assert
tick-loop semantics without `asyncio.sleep`. The clock is owned by
`Engine` (not `tick.py`) so the FastMCP lifespan keeps the engine as
the single time source.

Both seams flow into `tick.py`. `tick_loop` consults
`engine.clock.monotonic()` instead of `time.monotonic()`. The overrun
counter and the checkpoint cadence become testable without wall-clock
delays.

## Consequences

Easier: scenario regression tests assert exact trajectories rather
than approximate ones; Monte Carlo (ADR-0020) becomes a small wrapper
that derives `seed + i` per run; the live VM and a developer laptop
agree on what "the same scenario" produces. The deterministic seam
also unblocks the conservation-law tests in ADR-0020: a Hypothesis
strategy can shrink toward the failing seed.

Harder: every subsystem constructor grows an `rng` keyword and every
test fixture that builds subsystems directly (a handful in
`tests/unit/test_*_subsystem.py`) needs the keyword. The
`numpy.random` global is grep-banned in source after this change so
the seam cannot rot. The `Clock` Protocol is new; adding it to the
"no change without ADR" list keeps drift contained.

Alternatives rejected:

- **Per-subsystem RNG, no central seed.** Splits the seed accounting
  across ten files; a controller cannot tell which subsystem's RNG
  has been re-seeded after a scenario reset.
- **Inject the clock at `tick.py` only.** Leaves `engine.start()` and
  the overrun checkpoint still reading the real clock; the FastMCP
  lifespan would have two time sources.

## Revisit triggers

- The estimator stack moves to true multi-state Kalman with
  cross-channel covariance; a single Generator may need to be split
  per estimator for hypothesis-style shrinking.
- The Monte Carlo dispatcher grows beyond ten parallel runs and the
  shared Generator becomes a contention point.
- A future deployment ships a real device whose noise sources are not
  drawable from a software RNG; the seam must allow injecting a
  hardware-noise observer.
