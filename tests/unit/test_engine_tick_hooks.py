"""Engine tick-hook seam (ADR 0040).

The hook is the attachment point for the stateful scenario session: an
observer registered on the engine sees every tick's context after the mode
has settled. Containment is the safety property -- a raising hook must
degrade the observer, never the tick (the tick loop is the spine that
auto-safing rides; ADR 0024, ADR 0027).
"""

from __future__ import annotations

from nous.engine import Engine
from nous.types import TickContext


def test_hook_sees_each_tick_context(engine: Engine) -> None:
    seen: list[TickContext] = []
    engine.add_tick_hook(seen.append)

    engine.tick()
    engine.tick()

    assert [ctx.tick for ctx in seen] == [1, 2]
    assert seen[0].dt_s == engine.dt_s
    assert seen[0].mode == engine.state.mode.value


def test_duplicate_registration_is_single_subscription(engine: Engine) -> None:
    seen: list[TickContext] = []
    engine.add_tick_hook(seen.append)
    engine.add_tick_hook(seen.append)

    engine.tick()

    assert len(seen) == 1


def test_remove_hook_stops_delivery_and_tolerates_unknown(engine: Engine) -> None:
    seen: list[TickContext] = []
    engine.add_tick_hook(seen.append)
    engine.tick()

    engine.remove_tick_hook(seen.append)
    engine.tick()
    assert len(seen) == 1

    # Removing a never-registered hook is a no-op, not a raise.
    engine.remove_tick_hook(lambda ctx: None)


def test_raising_hook_is_contained_and_counted(engine: Engine) -> None:
    seen: list[TickContext] = []

    def _boom(ctx: TickContext) -> None:
        raise RuntimeError("observer bug")

    engine.add_tick_hook(_boom)
    engine.add_tick_hook(seen.append)

    ctx = engine.tick()

    # The tick completed, the well-behaved hook still ran, and the failure
    # is visible on the snapshot rather than silent.
    assert ctx.tick == 1
    assert len(seen) == 1
    assert engine.tick_hook_errors == 1
    assert engine.snapshot()["tick_hook_errors"] == 1


def test_hook_error_counter_resets_per_boot(engine: Engine) -> None:
    def _boom(ctx: TickContext) -> None:
        raise RuntimeError("observer bug")

    engine.add_tick_hook(_boom)
    engine.tick()
    assert engine.tick_hook_errors == 1
    engine.remove_tick_hook(_boom)

    # A fresh run's hook health must not inherit a previous run's failures.
    engine.stop()
    engine.start()
    assert engine.tick_hook_errors == 0
