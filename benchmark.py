"""Developer-runnable microbenchmarks for the tick loop and audit sink.

Adapts the small-script discipline from ``6dof-ascent-sim/benchmark.py``:
no baseline comparison, no JSON, no regression tracking. The point is
that "did this PR slow the loop?" has a runnable answer that lives in
the repo. Hot paths covered today: one engine tick, one audit-log
fsync round trip, and a representative Kalman update. Add a section
when a new path becomes a bottleneck candidate; remove a section when
the underlying code moves out of the hot path.

Run with ``uv run python benchmark.py``. Expect single-digit microseconds
for the estimator updates, low-millisecond range for one full tick on
a developer laptop, and a few hundred microseconds per audited write
once the fsync latency is amortised.
"""

from __future__ import annotations

import tempfile
import timeit
from pathlib import Path

from nous.audit import AuditLogger, AuditRecord
from nous.engine import Engine
from nous.estimators.thermal import ThermalKalman
from nous.policy import Tier
from nous.types import Observation


def _bench(label: str, callable_: object, number: int) -> None:
    total_s = timeit.timeit(callable_, number=number)  # type: ignore[arg-type]
    us_per_call = total_s / number * 1e6
    print(f"  {label:<44} {us_per_call:>10.2f} us/call  ({number:>7d} iters)")


def bench_engine_tick() -> None:
    engine = Engine()
    engine.start()
    try:
        _bench("engine.tick (full ten-subsystem step)", engine.tick, number=5_000)
    finally:
        engine.stop()


def bench_estimator_update() -> None:
    k = ThermalKalman()
    obs = Observation(
        source="thermal",
        ts_s=0.0,
        payload={"junction_c": 50.0, "enclosure_c": 32.0},
        noise={"junction_c_sigma": 1.0, "enclosure_c_sigma": 0.5},
    )
    _bench("ThermalKalman.update (single observation)", lambda: k.update(obs), number=50_000)


def bench_audit_write() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "audit.jsonl"
        logger = AuditLogger(path)
        record = AuditRecord.from_output(
            tool="bench_tool",
            tier=Tier.READ_ONLY.value,
            args={"k": "v"},
            output='{"ok": true}',
        )

        def _write() -> None:
            logger.write(record)

        _bench("AuditLogger.write (fsync round trip)", _write, number=2_000)


def main() -> None:
    print("nous benchmark (timeit; no baselines tracked)")
    print("-" * 70)
    bench_estimator_update()
    bench_audit_write()
    bench_engine_tick()
    print("-" * 70)
    print("done")


if __name__ == "__main__":
    main()
