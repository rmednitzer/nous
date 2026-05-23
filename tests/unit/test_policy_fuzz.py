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

from nous.policy import PolicyMode, Tier, classify, decide

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
    if tool in {
        "device_info", "device_health", "state_get", "state_history",
        "power_status", "apu_status", "thermal_status", "comms_state",
        "comms_status", "position_status", "biometrics_status",
        "compute_status", "inference_status", "storage_status", "sensors_status",
        "self_model_assess", "self_estimator_status", "interop_formats",
        "scenario_status", "audit_summary",
    }:
        return
    if tool in {
        "scenario_pause", "scenario_resume", "scenario_reset", "tick_advance",
        "inference_local", "interop_encode", "interop_decode",
    }:
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
    tier, reason = classify(tool, {"irreversible": bogus_irreversible})
    if bogus_irreversible and tier is not Tier.IRREVERSIBLE:
        # Only fires for explicitly classified non-irreversible tools.
        assert tool in {
            "device_info", "device_health", "state_get", "state_history",
            "power_status", "apu_status", "thermal_status", "comms_state",
            "comms_status", "position_status", "biometrics_status",
            "compute_status", "inference_status", "storage_status", "sensors_status",
            "self_model_assess", "self_estimator_status", "interop_formats",
            "scenario_status", "audit_summary",
            "scenario_pause", "scenario_resume", "scenario_reset", "tick_advance",
            "inference_local", "interop_encode", "interop_decode",
            "scenario_load", "scenario_inject", "comms_send", "comms_publish",
            "inference_cloud", "inference_request", "self_model_publish",
            "state_transition", "request_transition",
        }
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
