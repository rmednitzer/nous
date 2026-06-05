"""Regenerate ``docs/tool-reference.md`` from the FastMCP server (BL-052).

Walks the FastMCP registry, emits one Markdown table row per tool, plus
a JSON-schema section so a downstream consumer (controller, conformance
report) can read the parameter shape without parsing the prose.

Usage:

.. code-block:: shell

    uv run python scripts/gen_tool_reference.py        # write to docs/tool-reference.md
    uv run python scripts/gen_tool_reference.py --check  # exit non-zero on drift

The ``--check`` flag is the CI hook: a contributor that adds a tool
without regenerating the reference fails the check.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from nous.config import Settings
from nous.policy import classify
from nous.server import build_server

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "docs" / "tool-reference.md"


def _tier_label(tool_name: str) -> str:
    tier, _ = classify(tool_name, {})
    return f"T{int(tier)}"


def _summary(description: str) -> str:
    """First sentence (or first line) of the tool docstring."""
    if not description:
        return ""
    text = description.strip().splitlines()[0]
    if "." in text:
        text = text.split(".", 1)[0] + "."
    return text


def _render(tools: Iterable[Mapping[str, Any]]) -> str:
    tools = sorted(tools, key=lambda t: t["name"])
    lines: list[str] = [
        "# Tool reference",
        "",
        "Generated from the FastMCP registry by",
        "`scripts/gen_tool_reference.py`. Hand-editing this file is",
        "discouraged: regenerate with `make schema` or",
        "`uv run python scripts/gen_tool_reference.py`. The docs site",
        "regenerates this file at build time; run `make schema` to refresh",
        "the committed copy after changing a tool's signature or docstring.",
        "",
        "| Tool | Tier | Summary |",
        "|------|------|---------|",
    ]
    for t in tools:
        lines.append(
            f"| `{t['name']}` | {_tier_label(t['name'])} | {_summary(t['description'])} |"
        )
    lines.append("")
    lines.append("Every tool runs through the audited runner. Output bodies are SHA-256")
    lines.append("hashed; the audit record never contains the body itself. See")
    lines.append("`src/nous/runner.py` and ADR-0001.")
    lines.append("")
    lines.append("## Parameter schemas")
    lines.append("")
    lines.append("Per-tool JSON Schema for the input shape. Generated from the FastMCP")
    lines.append("tool registry.")
    lines.append("")
    for t in tools:
        lines.append(f"### `{t['name']}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(t["parameters"], indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _collect_tools() -> list[dict[str, Any]]:
    cfg = Settings(
        home=Path("/tmp/nous-gen-tool-ref"),
        audit_path="/tmp/nous-gen-tool-ref/audit.jsonl",
        db_url="sqlite:///:memory:",
    )
    Path("/tmp/nous-gen-tool-ref").mkdir(parents=True, exist_ok=True)
    mcp = build_server(cfg)
    out: list[dict[str, Any]] = []
    for tool in mcp._tool_manager.list_tools():
        out.append(
            {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.parameters,
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if the on-disk file differs from the generated one",
    )
    args = parser.parse_args(argv)

    tools = _collect_tools()
    rendered = _render(tools)

    if args.check:
        if not TARGET.exists():
            print(f"missing {TARGET}; run without --check to write it", file=sys.stderr)
            return 1
        on_disk = TARGET.read_text(encoding="utf-8")
        if on_disk != rendered:
            print(
                f"{TARGET} is out of date; regenerate with "
                f"`uv run python scripts/gen_tool_reference.py`",
                file=sys.stderr,
            )
            return 1
        print("tool reference is up to date")
        return 0

    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET} ({len(tools)} tools)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
