"""Regenerate the backlog status summary (top of docs/backlog.md).

The v0.1 implementation reads the existing backlog and counts items by
state. The L1 implementation will also produce a Markdown table of
items per milestone.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

_LINE = re.compile(
    r"^- BL-(\d+[a-z]?)\s+\[(?P<state>[^\]]+)\]\s+\((?P<milestone>L\d)\)",
    re.MULTILINE,
)


def main() -> int:
    path = Path(__file__).resolve().parents[1] / "docs" / "backlog.md"
    text = path.read_text(encoding="utf-8")
    states: Counter[str] = Counter()
    milestones: Counter[str] = Counter()
    for match in _LINE.finditer(text):
        states[match.group("state")] += 1
        milestones[match.group("milestone")] += 1
    print(f"backlog: {sum(states.values())} items")
    for state, count in sorted(states.items()):
        print(f"  {state}: {count}")
    for milestone, count in sorted(milestones.items()):
        print(f"  {milestone}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
