"""Inference and cloud-cap tools (ADR 0021).

The local-path inference call (T1), the inference-subsystem totals read (T0),
and the Anthropic daily-cap status (T0), extracted from ``server.py``. Handler
bodies and docstrings are byte-faithful to the inline definitions they replace,
so the registered tool surface does not change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the inference and cloud-cap tools on ``mcp``."""
    cfg = app.settings

    @mcp.tool()
    async def inference_local(
        prompt: str,
        max_tokens: int = 128,
        ctx: Context | None = None,
    ) -> str:
        """Local-path inference. Returns the synthetic response plus latency,
        energy joules, and the token-rate the profile would have delivered."""

        async def _work() -> str:
            result = app.engine.inference.request_local(
                prompt, max_tokens=max_tokens
            )
            payload = {"model": "nous-local-mock", "prompt_len": len(prompt)}
            payload.update(result.to_dict())
            return json.dumps(payload)

        return await wrap(
            "inference_local",
            {"prompt_len": len(prompt), "max_tokens": int(max_tokens)},
            ctx,
            _work,
        )

    @mcp.tool()
    async def inference_status(ctx: Context | None = None) -> str:
        """Inference subsystem totals: calls, tokens, joules, last latency."""

        async def _work() -> str:
            truth = dict(app.engine.inference.truth())
            payload = {
                "local_calls": truth["local_calls"],
                "total_tokens": truth["total_tokens"],
                "total_energy_j": round(truth["total_energy_j"], 4),
                "last_latency_s": round(truth["last_latency_s"], 4),
                "last_rate_tok_per_s": round(truth["last_rate_tok_per_s"], 3),
                "tok_per_s_capacity": round(truth["tok_per_s_capacity"], 3),
                "energy_j_per_tok": round(truth["energy_j_per_tok"], 4),
                "continuous_rate": round(truth["continuous_rate"], 3),
            }
            return json.dumps(payload)

        return await wrap("inference_status", {}, ctx, _work)

    @mcp.tool()
    async def anthropic_cap_status(ctx: Context | None = None) -> str:
        """Surface the Anthropic daily call cap (BL-021).

        Returns a structured payload a self-driving controller can branch
        on: ``available`` says whether a cloud call would even be
        attempted (key configured + cap not exhausted); ``remaining``
        is the count today's budget will still admit. ``exhausted=true``
        is the signal to fall back to ``inference_local``.
        """

        async def _work() -> str:
            from ..anthropic_status import cap_status

            payload = cap_status(cfg)
            return json.dumps(payload)

        return await wrap("anthropic_cap_status", {}, ctx, _work)
