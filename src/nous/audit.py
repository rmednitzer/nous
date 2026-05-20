"""Append-only, output-hashed audit trail.

One JSON object per line. The output body is never written to disk -- only
its SHA-256 and byte length -- so the log is safe to ship off-host.
Arguments pass through a fixed redaction allowlist before they arrive.

The handler is rotation-safe (``logging.handlers.WatchedFileHandler``): on
Linux make ``audit.jsonl`` append-only with ``chattr +a`` and rotate it
with the bundled ``deploy/logrotate.conf``.

Audit failures must never break a tool call: if the sink cannot be opened
the logger degrades to stderr and records ``degraded=True``.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import sys
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


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def redact(args: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of ``args`` with sensitive keys masked.

    Values for any key matching the redaction pattern are replaced with the
    placeholder. Surviving string values are truncated to a fixed budget so
    a misbehaving caller cannot fill the log with one giant argument.
    """
    out: dict[str, Any] = {}
    for key, value in args.items():
        if _REDACT_KEYS.search(key):
            out[key] = _REDACT_PLACEHOLDER
            continue
        if isinstance(value, str) and len(value) > _MAX_ARG_LEN:
            out[key] = value[:_MAX_ARG_LEN] + f"...<truncated {len(value)}>"
        else:
            out[key] = value
    return out


class AuditRecord(BaseModel):
    """One audit line. Output body is recorded as a hash and length only."""

    ts: str = Field(default_factory=_now_iso)
    tool: str
    tier: int
    denied: bool = False
    args: dict[str, Any] = Field(default_factory=dict)
    output_sha256: str = ""
    output_len: int = 0
    exit_code: int | None = None
    request_id: str = ""
    client_id: str = ""

    @classmethod
    def from_output(
        cls,
        *,
        tool: str,
        tier: int,
        args: Mapping[str, Any],
        output: str,
        denied: bool = False,
        exit_code: int | None = None,
        request_id: str = "",
        client_id: str = "",
    ) -> AuditRecord:
        return cls(
            tool=tool,
            tier=tier,
            denied=denied,
            args=dict(args),
            output_sha256=_sha256_hex(output),
            output_len=len(output.encode("utf-8", "replace")),
            exit_code=exit_code,
            request_id=request_id,
            client_id=client_id,
        )


class AuditLogger:
    """Writes structured audit records. Construction never raises."""

    def __init__(self, path: str | Path, also_stderr: bool = False) -> None:
        self.path = str(path)
        self.degraded = False
        self.degraded_reason = ""
        self._log = logging.getLogger("nous.audit")
        self._log.setLevel(logging.INFO)
        self._log.propagate = False
        for handler in list(self._log.handlers):
            self._log.removeHandler(handler)

        sink: logging.Handler
        try:
            target = Path(self.path).expanduser()
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(target), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
            with contextlib.suppress(OSError):
                target.chmod(0o600)
            sink = WatchedFileHandler(str(target), encoding="utf-8")
        except OSError as exc:
            self.degraded = True
            self.degraded_reason = str(exc)
            sink = logging.StreamHandler(sys.stderr)
        sink.setFormatter(logging.Formatter("%(message)s"))
        self._log.addHandler(sink)

        if also_stderr and not self.degraded:
            echo = logging.StreamHandler(sys.stderr)
            echo.setFormatter(logging.Formatter("AUDIT %(message)s"))
            self._log.addHandler(echo)

    def write(self, record: AuditRecord) -> None:
        """Append one audit line. Best-effort; swallows its own errors."""
        with contextlib.suppress(Exception):
            self._log.info(record.model_dump_json())
