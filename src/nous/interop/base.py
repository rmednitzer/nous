"""Interop adapter Protocol: ``encode / decode``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, runtime_checkable

__all__ = ["Adapter"]


@runtime_checkable
class Adapter(Protocol):
    """An adapter encodes nous state to an external format and back.

    ``encode`` returns a serialised payload (bytes). ``decode`` parses an
    inbound payload back to a structured mapping. Streaming adapters can
    expose their own ``stream()`` coroutine; the base Protocol stays
    minimal so adapters can be tested in isolation.
    """

    name: str

    def encode(self, data: Mapping[str, Any]) -> bytes: ...

    def decode(self, payload: bytes) -> Mapping[str, Any]: ...
