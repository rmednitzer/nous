"""Unit tests for the Anthropic call cap and prompt-cache plumbing.

Closes AUDIT.md H1 for `src/nous/anthropic_client.py`. The four scenarios
called out in the audit recommendation are covered: cap exhaustion, UTC
rollover, concurrent multiprocess locking, and corrupted-state recovery.
The concurrent-locking test is the regression test that pins AUDIT.md
C1 closed: the legacy ordering released the flock before flushing the
buffer, so a second process could acquire the lock, read stale
(pre-flush) state, re-read the same base count, and overwrite the
first process's increment. The symptom on disk is a lost update; the
operational symptom is that the daily cap can be bypassed because the
on-disk count grows more slowly than actual calls. The patched
ordering flushes and fsyncs inside the locked region, so N workers
that each call `increment()` K times must leave the on-disk counter
at exactly N*K.

The cap tests exercise `CallCap` directly; the `call` tests (BL-069,
ADR 0035) drive `AnthropicClient.call` against a fake `AsyncAnthropic`,
so CI never reaches the network while still pinning the tier guard,
streaming branch, cache markers, and surfaced cache-read tokens.
"""

from __future__ import annotations

import json
import multiprocessing as mp
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from anthropic import omit

from nous.anthropic_client import (
    AnthropicClient,
    CallCap,
    CapExhausted,
    CapPersistError,
)
from nous.config import Settings


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
    unpatched code path. The barrier wait is bounded so a sibling
    worker crashing during import surfaces as a non-zero exit code in
    the parent rather than stranding the cohort.
    """
    cap = CallCap(Path(path_str), cap=10_000)
    barrier.wait(timeout=20)  # type: ignore[attr-defined]
    for _ in range(iters):
        cap.increment()


def test_concurrent_increments_no_lost_updates(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    next_midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if (next_midnight - now).total_seconds() < 60:
        pytest.skip("Too close to UTC midnight; counter rollover would mask the race")

    path = tmp_path / "cap.json"
    ctx = mp.get_context("spawn")
    workers = 4
    iters_per_worker = 25
    barrier = ctx.Barrier(workers)
    procs = [
        ctx.Process(target=_bump_in_loop, args=(str(path), iters_per_worker, barrier))
        for _ in range(workers)
    ]
    try:
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=30)
    finally:
        for p in procs:
            if p.is_alive():
                p.terminate()
                p.join(timeout=5)
            if p.is_alive():
                p.kill()
                p.join(timeout=5)

    for p in procs:
        assert p.exitcode == 0, f"worker exited with {p.exitcode}"

    payload = json.loads(path.read_text())
    assert payload["count"] == workers * iters_per_worker


def test_peek_does_not_mutate(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=5)
    cap.increment()
    reading = cap.peek()
    assert reading.count == 1
    assert reading.cap == 5
    assert reading.corrupt is False
    assert cap.peek().count == 1


def test_peek_handles_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    cap = CallCap(path, cap=5)
    reading = cap.peek()
    assert reading.count == 0
    assert reading.cap == 5
    assert reading.corrupt is False


def test_peek_reports_corrupt_on_non_json(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    path.write_text("not valid json")
    reading = CallCap(path, cap=5).peek()
    assert reading.corrupt is True
    assert reading.cap == 5


def test_peek_reports_corrupt_on_non_integer_count(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path.write_text(json.dumps({"date": today, "count": "lots"}))
    assert CallCap(path, cap=5).peek().corrupt is True


def test_peek_reports_corrupt_on_negative_count(tmp_path: Path) -> None:
    # A well-formed JSON object whose count is out of domain (negative, or a
    # bool/float that int() would otherwise coerce) is corrupt, not coerced:
    # the counter file is attacker-clobberable, so a bad value must fail closed.
    path = tmp_path / "cap.json"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path.write_text(json.dumps({"date": today, "count": -1}))
    assert CallCap(path, cap=5).peek().corrupt is True
    with pytest.raises(CapExhausted, match="corrupt"):
        CallCap(path, cap=5).increment()


def test_peek_fresh_on_non_dict_json(tmp_path: Path) -> None:
    # Valid JSON that is not an object is the one shape increment() rewrites
    # as a fresh day rather than refusing, so peek must agree: count 0, intact.
    path = tmp_path / "cap.json"
    path.write_text("[1, 2, 3]")
    reading = CallCap(path, cap=5).peek()
    assert reading.corrupt is False
    assert reading.count == 0


def test_increment_fails_closed_on_non_integer_count(tmp_path: Path) -> None:
    path = tmp_path / "cap.json"
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    path.write_text(json.dumps({"date": today, "count": [1]}))
    with pytest.raises(CapExhausted, match="corrupt"):
        CallCap(path, cap=5).increment()


def test_fsync_failure_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "cap.json"
    cap = CallCap(path, cap=5)

    def _fail_fsync(fd: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr("nous.anthropic_client.os.fsync", _fail_fsync)
    # A durability fault raises CapPersistError, distinct from CapExhausted, so
    # the fallback reports it honestly rather than as a spent budget (ADR 0056).
    with pytest.raises(CapPersistError, match="could not be fsynced"):
        cap.increment()


# --- AnthropicClient.call: enriched cloud leg (BL-069, ADR 0035) ------------
#
# A fake AsyncAnthropic stands in for the SDK so no request leaves the host.
# It records the kwargs each call site sends so a test can assert the tier
# guard, the create-vs-stream branch, and the cache markers.


class _FakeBlock:
    def __init__(self, type_: str, *, text: str = "", thinking: str = "") -> None:
        self.type = type_
        self.text = text
        self.thinking = thinking


class _FakeUsage:
    def __init__(self, cache_read: int | None) -> None:
        self.cache_read_input_tokens = cache_read


class _FakeMessage:
    def __init__(self, blocks: list[_FakeBlock], cache_read: int | None) -> None:
        self.content = blocks
        self.usage = _FakeUsage(cache_read)


class _FakeStream:
    def __init__(self, message: _FakeMessage) -> None:
        self._message = message

    async def __aenter__(self) -> _FakeStream:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get_final_message(self) -> _FakeMessage:
        return self._message


class _FakeMessages:
    def __init__(self, message: _FakeMessage, calls: dict[str, Any]) -> None:
        self._message = message
        self._calls = calls

    async def create(self, **kwargs: Any) -> _FakeMessage:
        self._calls["create"] = kwargs
        return self._message

    def stream(self, **kwargs: Any) -> _FakeStream:
        self._calls["stream"] = kwargs
        return _FakeStream(self._message)


class _FakeAsyncAnthropic:
    def __init__(self, message: _FakeMessage, calls: dict[str, Any]) -> None:
        self.messages = _FakeMessages(message, calls)
        self._calls = calls

    def with_options(self, **kwargs: Any) -> _FakeAsyncAnthropic:
        self._calls["with_options"] = kwargs
        return self


def _client_with_fake(
    config: Settings, tmp_path: Path, message: _FakeMessage
) -> tuple[AnthropicClient, dict[str, Any]]:
    calls: dict[str, Any] = {}
    client = AnthropicClient(config, cap_path=tmp_path / "cap.json")
    client._client = _FakeAsyncAnthropic(message, calls)  # type: ignore[assignment]
    return client, calls


async def test_call_default_tier_creates_without_thinking(
    config: Settings, tmp_path: Path
) -> None:
    message = _FakeMessage([_FakeBlock("text", text="hi there")], cache_read=42)
    client, calls = _client_with_fake(config, tmp_path, message)

    out = await client.call(prompt="q", system="sys", max_tokens=256)

    assert out == "hi there"
    assert "create" in calls and "stream" not in calls
    kwargs = calls["create"]
    assert kwargs["model"] == config.anthropic_model_default
    assert kwargs["thinking"] is omit  # Haiku default tier: no thinking block
    assert all(
        block.get("cache_control") == {"type": "ephemeral"}
        for block in kwargs["system"]
    )
    assert client.last_cache_read_input_tokens == 42
    assert CallCap(tmp_path / "cap.json", cap=100).peek().count == 1


async def test_call_streams_long_generation(config: Settings, tmp_path: Path) -> None:
    message = _FakeMessage([_FakeBlock("text", text="long answer")], cache_read=0)
    client, calls = _client_with_fake(config, tmp_path, message)

    out = await client.call(prompt="q", system="sys", max_tokens=3000)

    assert out == "long answer"
    assert "stream" in calls and "create" not in calls


async def test_advanced_tier_enables_adaptive_thinking(
    config: Settings, tmp_path: Path
) -> None:
    message = _FakeMessage([_FakeBlock("text", text="x")], cache_read=0)
    client, calls = _client_with_fake(config, tmp_path, message)

    await client.call(prompt="q", system="sys", tier="advanced", max_tokens=256)

    kwargs = calls["create"]
    assert kwargs["model"] == config.anthropic_model_advanced
    assert kwargs["thinking"] == {"type": "adaptive"}


async def test_thinking_off_omits_block_even_on_capable_tier(
    config: Settings, tmp_path: Path
) -> None:
    message = _FakeMessage([_FakeBlock("text", text="x")], cache_read=0)
    client, calls = _client_with_fake(config, tmp_path, message)

    await client.call(
        prompt="q", system="sys", tier="advanced", thinking=False, max_tokens=256
    )

    assert calls["create"]["thinking"] is omit


async def test_thinking_block_excluded_from_text(
    config: Settings, tmp_path: Path
) -> None:
    message = _FakeMessage(
        [
            _FakeBlock("thinking", thinking="private reasoning"),
            _FakeBlock("text", text="final answer"),
        ],
        cache_read=0,
    )
    client, _ = _client_with_fake(config, tmp_path, message)

    out = await client.call(prompt="q", system="sys", tier="advanced", max_tokens=256)

    assert out == "final answer"


async def test_cap_exhausted_blocks_the_sdk_call(
    config: Settings, tmp_path: Path
) -> None:
    message = _FakeMessage([_FakeBlock("text", text="must not return")], cache_read=0)
    capped = config.model_copy(update={"anthropic_daily_cap": 1})
    calls: dict[str, Any] = {}
    cap_path = tmp_path / "cap.json"
    client = AnthropicClient(capped, cap_path=cap_path)
    client._client = _FakeAsyncAnthropic(message, calls)  # type: ignore[assignment]
    CallCap(cap_path, cap=1).increment()  # consume the day's only slot

    with pytest.raises(CapExhausted):
        await client.call(prompt="q", system="sys", max_tokens=128)

    assert calls == {}  # SDK never reached
