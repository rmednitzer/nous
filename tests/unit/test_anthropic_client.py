"""Unit tests for the Anthropic call cap and prompt-cache plumbing.

Closes AUDIT.md H1 for `src/nous/anthropic_client.py`. The four scenarios
called out in the audit recommendation are covered: cap exhaustion, UTC
rollover, concurrent multiprocess locking, and corrupted-state recovery.
The concurrent-locking test is the regression test that pins AUDIT.md
C1 closed: the legacy ordering released the flock before flushing the
buffer, so a second process could observe stale state and double-count
the same day. The patch flushes and fsyncs inside the locked region,
so two processes that each increment once must leave the on-disk
counter at exactly 2.

The tests exercise `CallCap` directly; the Anthropic SDK is never
called.
"""

from __future__ import annotations

import json
import multiprocessing as mp
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nous.anthropic_client import CallCap, CapExhausted


def test_counter_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    a = CallCap(path, cap=5)
    n1, _ = a.increment()
    n2, _ = a.increment()
    assert n1 == 1
    assert n2 == 2
    b = CallCap(path, cap=5)
    n3, _ = b.increment()
    assert n3 == 3


def test_cap_raises_when_exhausted(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=2)
    cap.increment()
    cap.increment()
    with pytest.raises(CapExhausted, match="cap reached"):
        cap.increment()


def test_zero_cap_disabled(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=0)
    for _ in range(20):
        cap.increment()


def test_corrupt_state_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    path.write_text("not valid json")
    cap = CallCap(path, cap=5)
    with pytest.raises(CapExhausted, match="corrupt"):
        cap.increment()


def test_utc_rollover_resets_counter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=10)

    base = datetime(2026, 5, 23, 23, 59, 30, tzinfo=UTC)
    clock = {"now": base}

    class _FakeDatetime:
        @staticmethod
        def now(tz: object = None) -> datetime:
            return clock["now"]

    monkeypatch.setattr("nous.anthropic_client.datetime", _FakeDatetime)

    count_before, _ = cap.increment()
    assert count_before == 1
    before_payload = json.loads(path.read_text())
    assert before_payload == {"date": "2026-05-23", "count": 1}

    clock["now"] = base + timedelta(minutes=2)
    count_after, _ = cap.increment()
    assert count_after == 1
    after_payload = json.loads(path.read_text())
    assert after_payload == {"date": "2026-05-24", "count": 1}


def _bump_in_loop(path_str: str, iters: int, barrier: object) -> None:
    """Top-level worker for the multiprocess concurrency test.

    Top-level so `multiprocessing` with the spawn start method can
    pickle and re-import it in the child. The barrier synchronises the
    start of every worker so they contend for the flock together,
    maximising the race window between unlock and flush in the
    unpatched code path.
    """
    cap = CallCap(Path(path_str), cap=10_000)
    barrier.wait()  # type: ignore[attr-defined]
    for _ in range(iters):
        cap.increment()


def test_concurrent_increments_do_not_double_count(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    ctx = mp.get_context("spawn")
    workers = 4
    iters_per_worker = 25
    barrier = ctx.Barrier(workers)
    procs = [
        ctx.Process(target=_bump_in_loop, args=(str(path), iters_per_worker, barrier))
        for _ in range(workers)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
        assert p.exitcode == 0, f"worker exited with {p.exitcode}"

    payload = json.loads(path.read_text())
    assert payload["count"] == workers * iters_per_worker


def test_peek_does_not_mutate(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=5)
    cap.increment()
    count, total = cap.peek()
    assert count == 1
    assert total == 5
    count_again, _ = cap.peek()
    assert count_again == 1


def test_peek_handles_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    cap = CallCap(path, cap=5)
    count, total = cap.peek()
    assert count == 0
    assert total == 5


def test_fsync_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=5)

    def _fail_fsync(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("nous.anthropic_client.os.fsync", _fail_fsync)
    with pytest.raises(CapExhausted, match="could not be fsynced"):
        cap.increment()
