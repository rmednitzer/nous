"""The MkDocs ADR nav is generated, and every doc page is navigable (BL-097).

``docs/audit-2026-06-14b.md`` DOC-1: the hand-maintained ``nav:`` block in
``mkdocs.yml`` had drifted to list only ADRs 0000 through 0017, and a page absent
from the nav is only an INFO line under ``mkdocs build --strict``, so CI never
failed on it. ``scripts/gen_mkdocs_adr_nav.py`` now regenerates the ADR nav block
from each ADR's H1 title (the source the ADR index already uses). These tests are
the drift gate the ``--strict`` build cannot be: they run on every PR with the
unit suite, so a new ADR or a new reference page that is not wired into the nav
fails here rather than coasting through.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]
_DOCS = _ROOT / "docs"
_MKDOCS = _ROOT / "mkdocs.yml"

# Pages deliberately left out of the nav (audit DOC-1 "What remains out of the
# nav is deliberate"): the dated audit and review logs, a record set referenced
# by path and never browsed, and the per-scenario showcase pages, reached from
# the in-nav scenario gallery README.
_NAV_EXEMPT = (
    re.compile(r"^audit-\d{4}-\d{2}-\d{2}[a-z]?\.md$"),
    re.compile(r"^review-\d{4}-\d{2}-\d{2}[a-z]?\.md$"),
    re.compile(r"^showcase/scenarios/.+\.md$"),
)

_NAV_TARGET = re.compile(r":\s*([A-Za-z0-9_./-]+\.md)\s*$", re.MULTILINE)


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_mkdocs_adr_nav", _ROOT / "scripts" / "gen_mkdocs_adr_nav.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adr_nav_block_is_generated_and_current() -> None:
    gen = _load_generator()
    entries = gen.adr_nav_entries(_DOCS / "adr")
    current = _MKDOCS.read_text(encoding="utf-8")

    # No drift: regenerating the marked block reproduces the file byte for byte.
    assert gen.render(current, entries) == current, (
        "mkdocs.yml ADR nav is stale; run `make schema` to regenerate it."
    )

    # Coverage: exactly one nav entry per ADR file, each pointing at its file.
    adr_files = sorted((_DOCS / "adr").glob("[0-9][0-9][0-9][0-9]-*.md"))
    assert len(entries) == len(adr_files)
    for path in adr_files:
        assert f": adr/{path.name}" in current


def test_every_docs_page_is_in_nav_or_exempt() -> None:
    nav_targets = set(_NAV_TARGET.findall(_MKDOCS.read_text(encoding="utf-8")))

    missing: list[str] = []
    for path in sorted(_DOCS.rglob("*.md")):
        rel = path.relative_to(_DOCS).as_posix()
        if rel in nav_targets:
            continue
        if any(pattern.match(rel) for pattern in _NAV_EXEMPT):
            continue
        missing.append(rel)

    assert not missing, (
        "docs pages reachable by neither the MkDocs nav nor the exemption list; "
        "add each to the nav in mkdocs.yml, or to _NAV_EXEMPT if it is "
        f"intentionally unlisted: {missing}"
    )
