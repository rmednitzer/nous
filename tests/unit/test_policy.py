"""Policy classifier and admission tests."""

from __future__ import annotations

from nous.policy import PolicyMode, Tier, classify, decide


def test_read_only_tool_classifies_as_t0() -> None:
    tier, _ = classify("device_info", {})
    assert tier is Tier.READ_ONLY


def test_stateful_tool_classifies_as_t2() -> None:
    tier, _ = classify("scenario_load", {"path": "foo.yaml"})
    assert tier is Tier.STATEFUL


def test_irreversible_tool_classifies_as_t3() -> None:
    tier, _ = classify("db_reset", {})
    assert tier is Tier.IRREVERSIBLE


def test_unknown_tool_falls_back_to_stateful_additive_surface() -> None:
    # Additive-surface rule: an unclassified tool is treated as STATEFUL
    # so guarded mode refuses it unless an allow regex matches.
    tier, _ = classify("never_seen_before", {})
    assert tier is Tier.STATEFUL


def test_unknown_tool_refused_under_guarded_without_allow() -> None:
    tier, _ = classify("never_seen_before", {})
    decision = decide(tier, PolicyMode.GUARDED, probe="never_seen_before")
    assert not decision.allowed


def test_readonly_mode_refuses_stateful_calls() -> None:
    decision = decide(Tier.STATEFUL, PolicyMode.READONLY)
    assert not decision.allowed


def test_open_mode_admits_irreversible_calls() -> None:
    decision = decide(Tier.IRREVERSIBLE, PolicyMode.OPEN)
    assert decision.allowed


def test_guarded_mode_lifts_with_allow_regex() -> None:
    refused = decide(Tier.STATEFUL, PolicyMode.GUARDED, probe="scenario_load")
    assert not refused.allowed
    permitted = decide(
        Tier.STATEFUL, PolicyMode.GUARDED, allow=r"scenario_", probe="scenario_load"
    )
    assert permitted.allowed
