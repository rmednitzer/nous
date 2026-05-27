"""Property-based fuzzing of the policy classifier and admission logic.

The policy is a safety boundary -- a bug here lets a stateful tool through
under ``readonly`` mode, which would defeat the audit/refusal contract.
The properties below pin down the invariants:

* ``classify`` returns a known tier for every input it sees.
* Under ``readonly`` mode, only ``READ_ONLY`` tools are admitted.
* Under ``open`` mode, every tool is admitted (the policy is *not* a
  sandbox -- the contract is audit, not enforcement).
* ``deny`` regex always wins (defence in depth).
* The "additive surface rule": unclassified tools are STATEFUL, so
  guarded mode refuses them unless an explicit allow regex matches.
"""

from __future__ import annotations

import string

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from nous.policy import (
    _READ_ONLY_TOOLS,
    _REVERSIBLE_TOOLS,
    PolicyMode,
    Tier,
    classify,
    decide,
)

_tool_names = st.text(
    alphabet=string.ascii_lowercase + "_",
    min_size=1,
    max_size=40,
)


@given(tool=_tool_names)
def test_classify_returns_known_tier(tool: str) -> None:
    tier, reason = classify(tool, {})
    assert isinstance(tier, Tier)
    assert isinstance(reason, str)
    assert reason


@given(tool=_tool_names)
def test_readonly_mode_only_admits_read_only(tool: str) -> None:
    tier, _ = classify(tool, {})
    decision = decide(tier, PolicyMode.READONLY, probe=tool)
    if tier is Tier.READ_ONLY:
        assert decision.allowed
    else:
        assert not decision.allowed


@given(tool=_tool_names)
def test_open_mode_admits_everything_without_deny(tool: str) -> None:
    tier, _ = classify(tool, {})
    decision = decide(tier, PolicyMode.OPEN, probe=tool)
    assert decision.allowed


@given(tool=_tool_names, deny=st.sampled_from([".+", ".", "^"]))
@settings(suppress_health_check=[HealthCheck.too_slow])
def test_deny_regex_blocks_everything(tool: str, deny: str) -> None:
    # These regexes match any non-empty probe; the deny path must fire.
    tier, _ = classify(tool, {})
    decision = decide(tier, PolicyMode.OPEN, deny=deny, probe=tool)
    assert not decision.allowed


@given(tool=_tool_names)
def test_unknown_tool_blocked_by_guarded_without_allow(tool: str) -> None:
    # Derive the skip list from policy.py directly so a new T0 or T1
    # tool added there does not silently desync this test (the prior
    # hand-curated lists missed ``anthropic_cap_status`` and would
    # have missed every L2 tool addition going forward).
    if tool in _READ_ONLY_TOOLS or tool in _REVERSIBLE_TOOLS:
        return
    tier, _ = classify(tool, {})
    decision = decide(tier, PolicyMode.GUARDED, probe=tool)
    assert not decision.allowed


@given(
    tool=_tool_names,
    bogus_irreversible=st.booleans(),
)
def test_args_irreversible_promotes_unclassified(
    tool: str, bogus_irreversible: bool
) -> None:
    # Reserved tools keep their explicit classification, regardless of args.
    from nous.policy import _STATEFUL_TOOLS

    tier, reason = classify(tool, {"irreversible": bogus_irreversible})
    if bogus_irreversible and tier is not Tier.IRREVERSIBLE:
        # Only fires for explicitly classified non-irreversible tools.
        assert (
            tool in _READ_ONLY_TOOLS
            or tool in _REVERSIBLE_TOOLS
            or tool in _STATEFUL_TOOLS
        )
    assert isinstance(reason, str)


@given(
    tool=st.sampled_from(["db_reset", "state_force_shutdown", "audit_rotate"]),
    mode=st.sampled_from([PolicyMode.READONLY, PolicyMode.GUARDED]),
)
def test_irreversible_tools_refused_outside_open(
    tool: str, mode: PolicyMode
) -> None:
    tier, _ = classify(tool, {})
    decision = decide(tier, mode, probe=tool)
    assert not decision.allowed


@given(probe=st.text(alphabet=string.printable, min_size=0, max_size=64))
def test_invalid_deny_regex_fails_closed(probe: str) -> None:
    decision = decide(Tier.READ_ONLY, PolicyMode.OPEN, deny="(", probe=probe)
    assert not decision.allowed


@given(probe=st.text(alphabet=string.printable, min_size=0, max_size=64))
def test_invalid_allow_regex_fails_closed_under_guarded(probe: str) -> None:
    decision = decide(Tier.STATEFUL, PolicyMode.GUARDED, allow="(", probe=probe)
    assert not decision.allowed
