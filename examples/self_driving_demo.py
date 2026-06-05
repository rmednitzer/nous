"""Self-driving sim demo: claude.ai as the operator over a stdio MCP link.

Spawns ``nous serve`` as a subprocess speaking MCP over stdio, then drives
it from a small Anthropic client loop. The model is given the tool surface
and asked to plan and execute a short scenario (advance the tick, inspect
operator state, deploy the solar APU if available, report endurance).

This is a *minimal* working example; production usage routes through the
HTTP transport (OAuth-gated) instead of stdio. Run it with::

    NOUS_HOME=/tmp/nous-demo \\
    ANTHROPIC_API_KEY=sk-ant-... \\
    python examples/self_driving_demo.py

Tracking: BL-021.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SYSTEM_PROMPT = (
    "You are operating an edge-AI inference appliance (nous), a "
    "simulation-based digital twin. You have a set of MCP tools exposed by "
    "the twin. Each turn: read state, plan, act, and report. Keep replies short."
)


@asynccontextmanager
async def nous_session() -> Any:
    """Yield an ``mcp.ClientSession`` connected to a fresh ``nous serve``."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "nous", "serve"],
        env={**os.environ, "NOUS_TRANSPORT": "stdio"},
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        yield session


async def main() -> int:
    """Run a single-shot demo loop. Returns process exit code."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY not set; printing tool surface only.")
        async with nous_session() as session:
            tools = await session.list_tools()
            print(json.dumps([t.name for t in tools.tools], indent=2))
        return 0

    # Lazy import so the no-key path keeps working without anthropic installed.
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    async with nous_session() as session:
        tools_response = await session.list_tools()
        tool_defs = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema,
            }
            for t in tools_response.tools
        ]
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tool_defs,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Read device_info, then power_status, then "
                        "self_model_assess for 'endurance'. Summarise."
                    ),
                }
            ],
        )
        print(json.dumps(msg.model_dump(mode="json"), indent=2, default=str))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(main()))
