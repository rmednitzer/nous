"""Shared encode-then-transmit seam for the publish tools (ADR 0033, ADR 0041).

``comms_publish`` and ``self_model_publish`` publish the same way: encode a
mapping through a named interop adapter, then account the wire bytes against
a comms link's envelope. This helper owns that composition and its error
categories so the two tools cannot drift apart; the response shapes are the
ones ``comms_publish`` established (unknown adapter, ``stale_estimate``,
schema/value error, and the ``ok``/``payload_hex``/``bytes_accepted``
success body).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..engine import Engine


def encode_and_tx(
    engine: Engine,
    link_id: str,
    adapter: str,
    data: Mapping[str, Any],
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Encode ``data`` via ``adapter`` and transmit the bytes on ``link_id``.

    Returns a JSON-safe mapping. Encode failures are reported as
    ``{"ok": False, ...}`` and nothing is transmitted; on success ``ok``
    reflects whether the link accepted the bytes (an unknown or forced-down
    link accepts none), and ``payload_hex`` carries the wire form either
    way so the controller sees both the encoding and its effect on the
    link. ``extra`` keys (e.g. the self-model ``kind``) are merged into the
    success body.
    """
    from ..interop import StaleEstimateError, build_adapter

    try:
        impl = build_adapter(adapter)
    except KeyError as exc:
        return {"ok": False, "error": str(exc)}
    try:
        payload = impl.encode(dict(data))
    except StaleEstimateError as exc:
        return {
            "ok": False,
            "adapter": adapter,
            "error": "stale_estimate",
            "age_s": exc.age_s,
            "max_age_s": exc.max_age_s,
        }
    except (ValueError, TypeError) as exc:
        return {"ok": False, "adapter": adapter, "error": str(exc)}
    accepted = engine.comms.tx(link_id, len(payload))
    return {
        "ok": accepted > 0,
        "link_id": link_id,
        "adapter": adapter,
        **dict(extra or {}),
        "payload_hex": payload.hex(),
        "len": len(payload),
        "bytes_accepted": accepted,
    }
