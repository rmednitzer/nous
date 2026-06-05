"""Interop adapter tools (ADR 0021).

The adapter-registry read (T0) and the encode/decode codecs (T1, BL-041),
extracted from ``server.py``. Handler bodies and docstrings are byte-faithful
to the inline definitions they replace, so the registered tool surface does not
change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the interop adapter tools on ``mcp``."""

    @mcp.tool()
    async def interop_formats(ctx: Context | None = None) -> str:
        """List the interop adapters the server knows about."""

        async def _work() -> str:
            from ..interop import REGISTRY

            return json.dumps(
                {
                    "adapters": sorted(REGISTRY.keys()),
                    "note": "adapters live in src/nous/interop/",
                }
            )

        return await wrap("interop_formats", {}, ctx, _work)

    @mcp.tool()
    async def interop_encode(
        adapter: str,
        data: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Encode ``data`` via the named interop adapter (BL-041 / T1).

        Returns a structured response. On success: ``{"adapter": ...,
        "payload_hex": ..., "len": N}``. An unknown adapter returns
        ``{"error": ...}``; a stale estimate returns ``{"adapter": ...,
        "error": "stale_estimate", "age_s": ..., "max_age_s": ...}``; a
        schema or value error returns ``{"adapter": ..., "error": ...}``.
        The payload is hex-encoded so the wire bytes survive an MCP
        JSON-RPC trip without codec-related corruption.
        """

        async def _work() -> str:
            from ..interop import StaleEstimateError, build_adapter

            try:
                impl = build_adapter(adapter)
            except KeyError as exc:
                return json.dumps({"error": str(exc)})
            try:
                payload = impl.encode(dict(data or {}))
            except StaleEstimateError as exc:
                return json.dumps(
                    {
                        "adapter": adapter,
                        "error": "stale_estimate",
                        "age_s": exc.age_s,
                        "max_age_s": exc.max_age_s,
                    }
                )
            except (ValueError, TypeError) as exc:
                return json.dumps({"adapter": adapter, "error": str(exc)})
            return json.dumps(
                {
                    "adapter": adapter,
                    "payload_hex": payload.hex(),
                    "len": len(payload),
                }
            )

        return await wrap(
            "interop_encode", {"adapter": adapter, "data": dict(data or {})}, ctx, _work
        )

    @mcp.tool()
    async def interop_decode(
        adapter: str,
        payload_hex: str,
        ctx: Context | None = None,
    ) -> str:
        """Decode a hex-encoded payload via the named adapter (BL-041 / T1).

        On success returns ``{"adapter": ..., "decoded": ...}`` where
        ``decoded`` is the adapter's structured output (which may itself
        carry an ``{"error": ...}`` key the adapter chose to emit). An
        unknown adapter returns ``{"error": ...}``; a hex-decoding error
        returns ``{"adapter": ..., "error": "hex: ..."}``.
        """

        async def _work() -> str:
            from ..interop import build_adapter

            try:
                impl = build_adapter(adapter)
            except KeyError as exc:
                return json.dumps({"error": str(exc)})
            try:
                payload = bytes.fromhex(payload_hex)
            except ValueError as exc:
                return json.dumps({"adapter": adapter, "error": f"hex: {exc}"})
            decoded = impl.decode(payload)
            return json.dumps({"adapter": adapter, "decoded": dict(decoded)})

        return await wrap(
            "interop_decode",
            {"adapter": adapter, "payload_hex_len": len(payload_hex)},
            ctx,
            _work,
        )
