"""Engine-boundary clock seam (ADR 0019).

The engine and every component that needs the current time goes
through one of the :class:`Clock` implementations registered on the
engine. Default deployments use :class:`MonotonicClock`, which is a
thin wrapper around :func:`time.monotonic` and :func:`time.time`.
Tests that need to assert deterministic tick semantics without
real-time sleeps use :class:`VirtualClock`, which advances under
explicit caller control.

The seam is owned by :class:`nous.engine.Engine`; the tick loop in
``tick.py`` continues to use ``anyio.current_time`` for event-loop
integration (anyio's scheduler depends on it), so the clock seam
matters primarily for any component that wants a clock value
independently of the event loop, plus tests that assert
trajectory equality between runs.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

__all__ = ["Clock", "MonotonicClock", "VirtualClock"]


@runtime_checkable
class Clock(Protocol):
    """A monotonic + wall-clock pair, the only timing surface the
    engine consults outside the asyncio scheduler."""

    def monotonic(self) -> float:
        """Return a monotonically non-decreasing value in seconds."""

    def wall(self) -> float:
        """Return wall-clock seconds since the epoch (UTC)."""


class MonotonicClock:
    """Default clock: ``time.monotonic`` plus ``time.time``."""

    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> float:
        return time.time()


class VirtualClock:
    """Test clock: the caller drives the time line.

    Both ``monotonic`` and ``wall`` advance together so a test does
    not have to track two counters. The default start is ``0.0`` so
    a test can assert exact differences from zero without wall-clock
    noise.
    """

    def __init__(self, start_s: float = 0.0) -> None:
        self._t = float(start_s)

    def monotonic(self) -> float:
        return self._t

    def wall(self) -> float:
        return self._t

    def advance(self, dt_s: float) -> None:
        """Move both monotonic and wall forward by ``dt_s`` seconds.

        Negative or zero values are rejected: a monotonic clock that
        moves backwards is the kind of footgun this seam exists to
        prevent.
        """
        if dt_s <= 0.0:
            raise ValueError(
                f"VirtualClock.advance requires dt_s > 0; got {dt_s}"
            )
        self._t += float(dt_s)
