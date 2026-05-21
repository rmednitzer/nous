"""Daily-call-cap persistence under stress.

Closes D-03: the legacy ``"a+"`` open mode produced unreliable
``seek/truncate/write`` behaviour and the corruption-recovery branch
silently reset the counter, defeating SC-5.

The tests below pin:

* The counter actually persists across CallCap instances.
* Reaching the cap raises CapExhausted.
* A corrupted counter file raises CapExhausted instead of silently
  resetting to 0 (failing closed, per SC-5).
* `peek()` does not mutate the counter.
"""

from __future__ import annotations

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
    with pytest.raises(CapExhausted):
        cap.increment()


def test_corrupt_state_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    path.write_text("{not-json")
    cap = CallCap(path, cap=5)
    with pytest.raises(CapExhausted, match="corrupt"):
        cap.increment()


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


def test_zero_cap_disabled(tmp_path: Path) -> None:
    # A cap of 0 means "no cap" -- never raise.
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=0)
    for _ in range(20):
        cap.increment()
