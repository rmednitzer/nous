"""Coverage check: every registered MCP tool is tier-classified exactly once.

ADR 0021 makes the tier classifier's coverage of the live tool surface a
test rather than a hand-maintained invariant. ``policy.classify`` falls back
to ``STATEFUL`` for any unclassified name (the additive-surface rule, ADR
0007), so a tool registered in ``server.py`` but never added to one of the
four tier frozensets would still be admitted, just at a silently defaulted
tier rather than the one its author intended. This test fails the moment
that drift appears: it walks the FastMCP surface and asserts every
registered tool sits in exactly one of the four frozensets.

The reverse direction is deliberately not asserted. The frozensets carry
forward-classifications (``inference_cloud``, ``state_force_shutdown``, and
the other not-yet-built names) so a tool lands at its intended authority
instead of the STATEFUL default when it ships; a name classified but not yet
registered is intended, not drift.
"""

from __future__ import annotations

import pytest

from nous.policy import (
    _IRREVERSIBLE_TOOLS,
    _READ_ONLY_TOOLS,
    _REVERSIBLE_TOOLS,
    _STATEFUL_TOOLS,
)
from nous.server import build_server

_TIER_SETS: dict[str, frozenset[str]] = {
    "READ_ONLY": _READ_ONLY_TOOLS,
    "REVERSIBLE": _REVERSIBLE_TOOLS,
    "STATEFUL": _STATEFUL_TOOLS,
    "IRREVERSIBLE": _IRREVERSIBLE_TOOLS,
}


@pytest.mark.asyncio
async def test_every_registered_tool_is_classified_exactly_once(
    tmp_nous_home: object,
) -> None:
    server = build_server()
    names = sorted(t.name for t in await server.list_tools())
    assert names, "FastMCP should advertise the v0.1 tool surface"

    unclassified: list[str] = []
    multiclassified: dict[str, list[str]] = {}
    for name in names:
        tiers = [tier for tier, members in _TIER_SETS.items() if name in members]
        if not tiers:
            unclassified.append(name)
        elif len(tiers) > 1:
            multiclassified[name] = tiers

    assert not unclassified, (
        "registered tools have no explicit tier and would default to STATEFUL "
        f"via the additive-surface rule: {unclassified}. Add each to the right "
        "frozenset in src/nous/policy.py."
    )
    assert not multiclassified, (
        f"registered tools classified in more than one tier: {multiclassified}"
    )


def test_tier_frozensets_are_pairwise_disjoint() -> None:
    tiers = list(_TIER_SETS.items())
    for i, (a_name, a_set) in enumerate(tiers):
        for b_name, b_set in tiers[i + 1 :]:
            overlap = a_set & b_set
            assert not overlap, (
                f"tier sets {a_name} and {b_name} overlap on {sorted(overlap)}; "
                "classify() resolves overlaps by priority order and would "
                "silently mistier the name."
            )
