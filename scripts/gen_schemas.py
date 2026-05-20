"""Regenerate JSON Schemas for the public Pydantic models.

Emits to ``docs/schema/``. The L1 implementation walks every Pydantic
model under ``src/nous`` and writes one JSON Schema per model.
"""

from __future__ import annotations

import json
from pathlib import Path

from nous.audit import AuditRecord
from nous.scenarios.loader import Scenario


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "docs" / "schema"
    out.mkdir(parents=True, exist_ok=True)
    schemas = {
        "audit-record.json": AuditRecord.model_json_schema(),
        "scenario.json": Scenario.model_json_schema(),
    }
    for name, schema in schemas.items():
        (out / name).write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
