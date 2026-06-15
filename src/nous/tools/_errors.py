"""Shared error-text redaction for tool bodies (BL-106).

A tool that catches an exception inside its ``_work`` coroutine and returns a
structured error must not echo ``str(exc)``: the message can carry
payload-derived text, while the runner only redacts exceptions that *escape*
``work`` (it stamps the class name, see ``runner.py``). ``error_class`` gives the
caught-and-returned path the same class-name redaction, so the two are
consistent and neither leaks a message.
"""

from __future__ import annotations


def error_class(exc: BaseException) -> str:
    """The exception's class name (e.g. ``"ValueError"``), never its message."""
    return type(exc).__name__
