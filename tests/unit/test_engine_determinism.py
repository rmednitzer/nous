"""Engine-boundary seed and clock seams (ADR 0019).

The seams give the test suite a hook for asserting trajectory
equality under a fixed seed (``test_same_seed_same_trajectory``)
and for driving the clock under explicit control without
``asyncio.sleep`` (``test_virtual_clock_drives_time_line``). The
default-no-args path stays equivalent to pre-ADR behaviour.
"""

from __future__ import annotations

from pathlib import Path

from nous.clocks import MonotonicClock, VirtualClock
from nous.engine import Engine


def test_engine_default_clock_is_monotonic(tmp_nous_home: Path) -> None:
    engine = Engine()
    assert isinstance(engine.clock, MonotonicClock)
    # The default seed is None (OS entropy); the engine still
    # creates a Generator so downstream callers can take it.
    assert engine.rng is not None


def test_virtual_clock_drives_time_line(tmp_nous_home: Path) -> None:
    clock = VirtualClock(start_s=100.0)
    engine = Engine(clock=clock)

    assert engine.clock.monotonic() == 100.0
    assert engine.clock.wall() == 100.0
    clock.advance(5.0)
    assert engine.clock.monotonic() == 105.0
    assert engine.clock.wall() == 105.0


def test_same_seed_produces_identical_comms_filter_state(
    tmp_nous_home: Path,
) -> None:
    """Two engines built with the same seed produce identical
    comms-particle-filter belief state after the same number of
    ticks. Without the seam, the per-instance default ``seed=0``
    of ``CommsParticleFilter`` made this accidentally true; with
    the seam the engine's RNG flows into the filter and the
    invariant is intentional."""
    engine_a = Engine(seed=42)
    engine_b = Engine(seed=42)
    engine_a.start()
    engine_b.start()
    try:
        for _ in range(10):
            engine_a.tick()
            engine_b.tick()
        state_a = engine_a.comms_est.state()
        state_b = engine_b.comms_est.state()
        assert state_a == state_b
    finally:
        engine_a.stop()
        engine_b.stop()


def test_different_seeds_diverge_under_resampling(tmp_nous_home: Path) -> None:
    """Different seeds drive divergent particle-filter
    trajectories. This is the negative half of the determinism
    contract: a controller that expects "different seed, different
    sample path" can rely on it."""
    engine_a = Engine(seed=1)
    engine_b = Engine(seed=2)
    engine_a.start()
    engine_b.start()
    try:
        # Force the particle filter to resample by driving a
        # link-loss scenario that biases observations away from
        # the prior.
        for engine in (engine_a, engine_b):
            link_ids = engine.comms.link_ids
            if link_ids:
                engine.comms.set_link_state(link_ids[0], connected=False)
        for _ in range(30):
            engine_a.tick()
            engine_b.tick()
        state_a = engine_a.comms_est.state()
        state_b = engine_b.comms_est.state()
        # The connected_links_belief is the soft sum of particle
        # weights; under different seeds the resampling stream
        # produces different beliefs. We assert difference rather
        # than equality so a future tightening of the filter's
        # noise model does not break the test.
        assert state_a != state_b
    finally:
        engine_a.stop()
        engine_b.stop()
