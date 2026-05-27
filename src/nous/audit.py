"""Append-only, output-hashed audit trail.

One JSON object per line. The output body is never written to disk -- only
its SHA-256 and byte length -- so the log is safe to ship off-host.
Arguments pass through a fixed redaction allowlist before they arrive.

The handler is rotation-safe (``logging.handlers.WatchedFileHandler``): on
Linux make ``audit.jsonl`` append-only with ``chattr +a`` and rotate it
with the bundled ``deploy/logrotate.conf``.

Durability under SIGTERM and hard power loss: every write flushes Python
buffers and ``os.fsync()``s the underlying file descriptor so the audit
line is on stable storage before the call returns. ``fsync`` failures are
logged to stderr and the handler is marked degraded -- the operator gets
an observable signal that a record may have been lost.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from logging.handlers import WatchedFileHandler
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["AuditLogger", "AuditRecord", "redact"]


_REDACT_KEYS = re.compile(
    r"(?i)(authorization|cookie|token|password|secret|api[_-]?key|bearer)"
)
_REDACT_PLACEHOLDER = "<REDACTED>"
_MAX_ARG_LEN = 4096

# AUDIT-2026-05-23 N2 follow-up B: auto-resync schedule. Initial 5
# seconds gives an operator who is actively diagnosing a small
# window to call ``audit_resync`` themselves or kill the service
# before the auto-retry fires; the 300-second cap keeps a
# long-running degraded state from hammering the filesystem.
_INITIAL_AUTO_RESYNC_BACKOFF_S = 5.0
_MAX_AUTO_RESYNC_BACKOFF_S = 300.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def redact(args: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``args`` with sensitive keys masked at every depth.

    Values for any key matching the redaction pattern are replaced with the
    placeholder. The walk recurses into nested mappings and list items so
    a caller cannot smuggle a secret past the allowlist by burying it
    inside ``{"context": {"headers": {"Authorization": ...}}}``. Surviving
    string values are truncated to a fixed budget at every depth so a
    misbehaving caller cannot fill the log with one giant argument.

    Closes AUDIT-2026-05-20 C2.
    """
    return _redact_mapping(args)


def _redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, inner in value.items():
        if _REDACT_KEYS.search(key):
            out[key] = _REDACT_PLACEHOLDER
        else:
            out[key] = _redact_value(inner)
    return out


def _redact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str) and len(value) > _MAX_ARG_LEN:
        return value[:_MAX_ARG_LEN] + f"...<truncated {len(value)}>"
    return value


class AuditRecord(BaseModel):
    """One audit line. Output body is recorded as a hash and length only.

    Schema is shaped for EU AI Act Art. 12 (automatic recording of events)
    and CRA Art. 13 (security logging). Each line is self-describing
    (``ts``, ``tool``, ``tier``, ``policy_mode``, ``decision_reason``,
    ``denied``, ``args``, ``output_sha256``) so a conformity-assessment
    body can replay the trail without consulting the source code.
    """

    ts: str = Field(default_factory=_now_iso)
    tool: str
    tier: int
    denied: bool = False
    decision_reason: str = ""
    policy_mode: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    output_sha256: str = ""
    output_len: int = 0
    exit_code: int | None = None
    request_id: str = ""
    client_id: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_output(
        cls,
        *,
        tool: str,
        tier: int,
        args: Mapping[str, Any],
        output: str,
        denied: bool = False,
        decision_reason: str = "",
        policy_mode: str = "",
        exit_code: int | None = None,
        request_id: str = "",
        client_id: str = "",
        extra: Mapping[str, Any] | None = None,
    ) -> AuditRecord:
        return cls(
            tool=tool,
            tier=tier,
            denied=denied,
            decision_reason=decision_reason,
            policy_mode=policy_mode,
            args=dict(args),
            output_sha256=_sha256_hex(output),
            output_len=len(output.encode("utf-8", "replace")),
            exit_code=exit_code,
            request_id=request_id,
            client_id=client_id,
            extra=dict(extra) if extra else {},
        )


class _FsyncingFileHandler(WatchedFileHandler):
    """``WatchedFileHandler`` that fsyncs the descriptor after every emit.

    On SIGTERM and hard power loss the OS may evict the page cache before
    a buffered write reaches stable storage. The audit log is the only
    record we ship off-host, so the audit handler trades a small per-record
    latency cost for end-to-end durability. ``fsync`` failures bubble up to
    the parent handler's :meth:`handleError`, which marks the logger
    degraded via ``stream.fsync_failed``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fsync_failures = 0
        self.last_fsync_error = ""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        stream = self.stream
        if stream is None:
            return
        try:
            stream.flush()
            fd = stream.fileno()
        except (OSError, ValueError):
            return
        try:
            os.fsync(fd)
        except OSError as exc:
            self.fsync_failures += 1
            self.last_fsync_error = str(exc)
            with contextlib.suppress(Exception):
                sys.stderr.write(f"audit fsync failed: {exc}\n")
                sys.stderr.flush()


class AuditLogger:
    """Writes structured audit records. Construction never raises."""

    def __init__(self, path: str | Path, also_stderr: bool = False) -> None:
        self.path = str(path)
        self.degraded = False
        self.degraded_reason = ""
        self.fsync_failures = 0
        # AUDIT-2026-05-23 N2 follow-up: track cumulative writes and the
        # most recent successful write timestamp so ``audit_summary`` can
        # surface activity to the controller without parsing the JSONL
        # tail. ``writes_total`` advances only on durable writes (gated
        # on the ``_sync_fsync_failure_state`` delta); a controller
        # watching this counter against the tick cadence can detect
        # "everything is quiet" vs "the handler is silently dropping."
        self.writes_total = 0
        self.last_write_ts_s: float | None = None
        # AUDIT-2026-05-23 N2 follow-up B: opportunistic auto-resync
        # with exponential backoff. When the sink is degraded and a
        # ``write()`` lands, the handler attempts an in-process
        # re-open subject to the backoff schedule. Recovery resets
        # the backoff to ``_INITIAL_AUTO_RESYNC_BACKOFF_S``; failure
        # doubles the wait up to ``_MAX_AUTO_RESYNC_BACKOFF_S``. The
        # cadence is monotonic-clock-based so wall-time jitter does
        # not change the schedule. Operators see the next-attempt
        # countdown via ``audit_summary.auto_resync_due_in_s``.
        self.auto_resync_attempts = 0
        self.last_auto_resync_ts_s: float | None = None
        self._auto_resync_backoff_s = _INITIAL_AUTO_RESYNC_BACKOFF_S
        self._next_auto_resync_at_monotonic_s: float | None = None
        self._seen_handler_fsync_failures = 0
        self._also_stderr = bool(also_stderr)
        self._log = logging.getLogger("nous.audit")
        self._log.setLevel(logging.INFO)
        self._log.propagate = False
        for handler in list(self._log.handlers):
            self._log.removeHandler(handler)
        self._open_sink()

    def _open_sink(self) -> None:
        """Attach a fresh handler stack for the current ``self.path``.

        Splits the sink-opening logic out of ``__init__`` so
        :meth:`resync` can re-run it without re-allocating the
        logger or the in-process counters. ``__init__`` calls this
        once at construction; ``resync`` calls it again whenever an
        operator wants to clear a degraded state without restarting
        the process.
        """
        for handler in list(self._log.handlers):
            self._log.removeHandler(handler)
            with contextlib.suppress(Exception):
                handler.close()
        self._seen_handler_fsync_failures = 0

        sink: logging.Handler
        try:
            target = Path(self.path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            # Open then close just to assert the file exists with the
            # right mode bits before any record gets written.
            fd = os.open(
                str(target), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600
            )
            os.close(fd)
            with contextlib.suppress(OSError):
                target.chmod(0o600)
            sink = _FsyncingFileHandler(str(target), encoding="utf-8")
            self.degraded = False
            self.degraded_reason = ""
        except OSError as exc:
            self.degraded = True
            self.degraded_reason = str(exc)
            sink = logging.StreamHandler(sys.stderr)
        sink.setFormatter(logging.Formatter("%(message)s"))
        self._log.addHandler(sink)

        if self._also_stderr and not self.degraded:
            echo = logging.StreamHandler(sys.stderr)
            echo.setFormatter(logging.Formatter("AUDIT %(message)s"))
            self._log.addHandler(echo)

    def resync(self) -> dict[str, Any]:
        """Attempt to re-open the audit sink in place.

        Closes AUDIT-2026-05-23 N2 (live audit sink stuck degraded
        until process restart). An operator (or the ``audit_resync``
        MCP tool) calls this after fixing the underlying filesystem
        issue (permissions, mount, ``ReadWritePaths=`` drift). The
        returned status mirrors the ``audit_summary`` shape:

            {
                "path": "/var/log/nous/audit.jsonl",
                "degraded": false,
                "degraded_reason": "",
                "fsync_failures": 3,   # cumulative; not reset
                "recovered": true,     # true when this call cleared
                                       # a previously-degraded state
            }

        ``fsync_failures`` is the cumulative counter and is not
        reset, so an operator can still see how many writes were
        lost during the degraded window. ``recovered`` distinguishes
        "this call fixed the sink" from "the sink was already
        healthy and no-op-ed."

        A successful resync also clears the auto-resync backoff
        state (the next degradation starts at
        ``_INITIAL_AUTO_RESYNC_BACKOFF_S`` again, not the doubled
        cap).
        """
        was_degraded = bool(self.degraded)
        self._open_sink()
        recovered = was_degraded and not self.degraded
        if not self.degraded:
            self._reset_auto_resync_state()
        return {
            "path": self.path,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "fsync_failures": self.fsync_failures,
            "recovered": recovered,
        }

    def _reset_auto_resync_state(self) -> None:
        """Restore the auto-resync backoff schedule to the initial state."""
        self._auto_resync_backoff_s = _INITIAL_AUTO_RESYNC_BACKOFF_S
        self._next_auto_resync_at_monotonic_s = None

    def _maybe_auto_resync(self) -> None:
        """Opportunistically re-open a degraded sink on the backoff schedule.

        Called from :meth:`write` before each emit. The check is
        cheap when healthy (one ``self.degraded`` test) and
        ``time.monotonic`` is the only system call when degraded
        but not yet due. The contract:

        - Healthy: reset backoff state, return.
        - Degraded but not yet scheduled: schedule the first
          attempt for ``_INITIAL_AUTO_RESYNC_BACKOFF_S`` from now.
        - Degraded and scheduled, not due: return.
        - Degraded and due: ``_open_sink()``. On recovery, reset
          backoff; on continued failure, double the wait up to
          ``_MAX_AUTO_RESYNC_BACKOFF_S`` and schedule the next
          attempt.

        The auto-resync tally and last-attempt timestamp surface
        through ``summary()`` so an operator who is actively
        diagnosing can see when the next retry will fire.
        """
        if not self.degraded:
            self._reset_auto_resync_state()
            return
        now_monotonic = time.monotonic()
        if self._next_auto_resync_at_monotonic_s is None:
            self._auto_resync_backoff_s = _INITIAL_AUTO_RESYNC_BACKOFF_S
            self._next_auto_resync_at_monotonic_s = (
                now_monotonic + self._auto_resync_backoff_s
            )
            return
        if now_monotonic < self._next_auto_resync_at_monotonic_s:
            return
        self.auto_resync_attempts += 1
        with contextlib.suppress(Exception):
            self.last_auto_resync_ts_s = time.time()
        self._open_sink()
        if self.degraded:
            self._auto_resync_backoff_s = min(
                self._auto_resync_backoff_s * 2.0,
                _MAX_AUTO_RESYNC_BACKOFF_S,
            )
            self._next_auto_resync_at_monotonic_s = (
                now_monotonic + self._auto_resync_backoff_s
            )
        else:
            self._reset_auto_resync_state()

    def write(self, record: AuditRecord) -> None:
        """Append one audit line. Best-effort; swallows its own errors.

        The handler fsyncs after every record. If the underlying file
        operation raises, the exception is caught here -- audit failures
        must never break a tool call -- but the failure is tallied on
        ``self.fsync_failures`` and surfaced through ``device_info``.

        ``writes_total`` and ``last_write_ts_s`` advance only when the
        write was *durable*: the handler accepted the record AND
        ``_sync_fsync_failure_state`` saw no new fsync failures.

        Before the write, ``_maybe_auto_resync`` runs to give a
        degraded sink a chance to recover so the incoming record
        lands durably (AUDIT-2026-05-23 N2 follow-up B).
        """
        self._maybe_auto_resync()
        try:
            self._log.info(record.model_dump_json())
            new_failures = self._sync_fsync_failure_state()
            if new_failures == 0:
                self.writes_total += 1
                with contextlib.suppress(Exception):
                    self.last_write_ts_s = time.time()
        except OSError as exc:
            self.fsync_failures += 1
            self.degraded = True
            self.degraded_reason = str(exc)
            with contextlib.suppress(Exception):
                sys.stderr.write(f"audit write failed: {exc}\n")
        except Exception as exc:  # noqa: BLE001
            self.fsync_failures += 1
            self.degraded = True
            self.degraded_reason = exc.__class__.__name__
            with contextlib.suppress(Exception):
                sys.stderr.write(f"audit write degraded: {exc.__class__.__name__}\n")

    def summary(self) -> dict[str, Any]:
        """Return the read-only view of the audit handler's state.

        The shape is the T0 surface ``audit_summary`` exposes. The
        controller calls this to confirm the sink is healthy without
        having to read the JSONL tail or correlate ``device_info``
        with ``device_health``. Fields:

            path                  -- the audit file path (same as
                                     ``device_info.audit.path``)
            degraded              -- True when the handler last failed
                                     to write / fsync
            degraded_reason       -- last failure reason; "" when healthy
            fsync_failures        -- cumulative; not reset on recovery
            writes_total          -- cumulative durable writes; a flat
                                     line plus tick activity is the
                                     silent-drop signal
            last_write_ts_s       -- unix timestamp of the most recent
                                     durable write; None when no
                                     writes yet
            also_stderr           -- True when a stderr echo handler
                                     is attached alongside the file
                                     sink (set at construction)
            auto_resync_attempts  -- cumulative count of automatic
                                     in-process re-opens triggered by
                                     a degraded write (PR #61 N2 B)
            last_auto_resync_ts_s -- unix timestamp of the most recent
                                     auto-resync attempt; None if no
                                     attempt has fired
            auto_resync_due_in_s  -- seconds until the next scheduled
                                     auto-resync attempt; None when
                                     the sink is healthy or has not
                                     yet failed a write since startup
        """
        next_at = self._next_auto_resync_at_monotonic_s
        due_in: float | None = (
            None if next_at is None else max(0.0, next_at - time.monotonic())
        )
        return {
            "path": self.path,
            "degraded": self.degraded,
            "degraded_reason": self.degraded_reason,
            "fsync_failures": self.fsync_failures,
            "writes_total": self.writes_total,
            "last_write_ts_s": self.last_write_ts_s,
            "also_stderr": self._also_stderr,
            "auto_resync_attempts": self.auto_resync_attempts,
            "last_auto_resync_ts_s": self.last_auto_resync_ts_s,
            "auto_resync_due_in_s": due_in,
        }

    def _sync_fsync_failure_state(self) -> int:
        """Sync handler-side fsync failures into the logger state.

        Returns the number of new failures observed since the last
        call (0 when the underlying handlers reported no new failures).
        ``write()`` uses this delta to gate the durable-write
        counters: a non-zero delta means the most recent emit
        failed its fsync and the counters must NOT advance.
        """
        fsync_handlers = [
            handler
            for handler in self._log.handlers
            if isinstance(handler, _FsyncingFileHandler)
        ]
        total_handler_failures = sum(handler.fsync_failures for handler in fsync_handlers)
        delta = total_handler_failures - self._seen_handler_fsync_failures
        if delta <= 0:
            return 0
        self.fsync_failures += delta
        self._seen_handler_fsync_failures = total_handler_failures
        self.degraded = True
        for handler in fsync_handlers:
            if handler.last_fsync_error:
                self.degraded_reason = handler.last_fsync_error
                break
        return delta

    def flush(self) -> None:
        """Force every handler to flush + fsync (called from systemd ExecStopPost)."""
        for handler in list(self._log.handlers):
            with contextlib.suppress(Exception):
                handler.flush()
            stream = getattr(handler, "stream", None)
            if stream is None:
                continue
            try:
                fd = stream.fileno()
            except (OSError, ValueError):
                continue
            with contextlib.suppress(OSError):
                os.fsync(fd)
