"""Regenerate ``docs/adr/README.md`` from ADR file headers."""

from __future__ import annotations

import re
from pathlib import Path

_ADR_HEADER = re.compile(r"^#\s+ADR\s+(\d+):\s+(.+?)\s*$", re.MULTILINE)
_STATUS = re.compile(r"^- \*\*Status:\*\*\s+(.+)$", re.MULTILINE)
_DATE = re.compile(r"^- \*\*Date:\*\*\s+(.+)$", re.MULTILINE)


def main() -> int:
    adr_dir = Path(__file__).resolve().parents[1] / "docs" / "adr"
    rows: list[tuple[str, str, str, str, str]] = []
    for path in sorted(adr_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        text = path.read_text(encoding="utf-8")
        header = _ADR_HEADER.search(text)
        status = _STATUS.search(text)
        date = _DATE.search(text)
        if not header:
            continue
        number = header.group(1)
        title = header.group(2)
        rows.append(
            (
                number,
                title,
                status.group(1) if status else "",
                date.group(1) if date else "",
                path.name,
            )
        )

    out = adr_dir / "README.md"
    lines = [
        "# Architecture Decision Records",
        "",
        "| # | Title | Status | Date |",
        "|---|-------|--------|------|",
    ]
    for number, title, status, date, name in rows:
        lines.append(f"| {number} | [{title}]({name}) | {status} | {date} |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
