"""Tiered-authority policy for the simulator's tool surface.

Every MCP tool is classified into a tier and then admitted or refused by the
configured policy mode. This is defence in depth, not a sandbox: with the
default ``open`` mode every tool is permitted but still classified and
audited; ``guarded`` refuses any T2/T3 tool unless an allow regex matches;
``readonly`` only admits T0.

Tiers:

* T0  READ_ONLY     (no state change)
* T1  REVERSIBLE    (trivially undone)
* T2  STATEFUL      (observable side effect)
* T3  IRREVERSIBLE  (rollback expensive or impossible)
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import IntEnum, StrEnum
from typing import Any, NamedTuple

__all__ = [
    "PolicyDecision",
    "PolicyDenied",
    "PolicyMode",
    "Tier",
    "classify",
    "decide",
]


class Tier(IntEnum):
    READ_ONLY = 0
    REVERSIBLE = 1
    STATEFUL = 2
    IRREVERSIBLE = 3


class PolicyMode(StrEnum):
    OPEN = "open"
    GUARDED = "guarded"
    READONLY = "readonly"


class PolicyDecision(NamedTuple):
    tier: Tier
    allowed: bool
    reason: str


class PolicyDenied(RuntimeError):
    """Raised by the runner when an admission check refuses the call."""


_READ_ONLY_TOOLS = frozenset(
    {
        "device_info",
        "device_health",
        "state_get",
        "state_history",
        "power_status",
        "apu_status",
        "thermal_status",
        "comms_state",
        "comms_status",
        "position_status",
        "biometrics_status",
        "compute_status",
        "inference_status",
        "storage_status",
        "sensors_status",
        "self_model_assess",
        "self_estimator_status",
        "interop_formats",
        "scenario_status",
        "audit_summary",
    }
)

_REVERSIBLE_TOOLS = frozenset(
    {
        "scenario_pause",
        "scenario_resume",
        "scenario_reset",
        "tick_advance",
        "inference_local",
        "interop_encode",
        "interop_decode",
    }
)

_STATEFUL_TOOLS = frozenset(
    {
        "scenario_load",
        "scenario_inject",
        "comms_send",
        "comms_publish",
        "inference_cloud",
        "inference_request",
        "self_model_publish",
        "state_transition",
        "request_transition",
    }
)

_IRREVERSIBLE_TOOLS = frozenset(
    {
        "state_force_shutdown",
        "state_force_fault",
        "audit_rotate",
        "db_reset",
    }
)


def classify(tool: str, args: Mapping[str, Any] | None = None) -> tuple[Tier, str]:
    """Best-effort tier for ``tool``.

    Additive-surface rule: an unknown tool is treated as ``STATEFUL`` so
    it requires an explicit allowlist match under guarded mode and is
    refused under readonly mode. A typo or a forgotten classification is
    therefore observable in CI (the guarded-mode tests fail) instead of
    silently coasting through under the old ``REVERSIBLE`` default.
    """
    if tool in _IRREVERSIBLE_TOOLS:
        return Tier.IRREVERSIBLE, "irreversible tool"
    if tool in _STATEFUL_TOOLS:
        return Tier.STATEFUL, "stateful tool"
    if tool in _REVERSIBLE_TOOLS:
        return Tier.REVERSIBLE, "reversible tool"
    if tool in _READ_ONLY_TOOLS:
        return Tier.READ_ONLY, "read-only tool"
    if args and bool(args.get("irreversible")):
        return Tier.IRREVERSIBLE, "args.irreversible flag set"
    return Tier.STATEFUL, "unclassified tool defaults to stateful (additive-surface rule)"


def decide(
    tier: Tier,
    mode: PolicyMode,
    *,
    deny: str = "",
    allow: str = "",
    probe: str = "",
) -> PolicyDecision:
    """Admit or refuse a call of the given tier under the given mode.

    ``deny`` (a regex) refuses unconditionally in every mode.
    ``allow`` (a regex) lifts a guarded T2/T3 refusal.
    """
    if deny:
        try:
            if re.search(deny, probe):
                return PolicyDecision(tier, False, "matched NOUS_POLICY_DENY")
        except re.error:
            return PolicyDecision(tier, False, "invalid NOUS_POLICY_DENY regex")

    if mode is PolicyMode.READONLY and tier is not Tier.READ_ONLY:
        return PolicyDecision(
            tier, False, f"readonly mode refuses Tier {int(tier)} ({tier.name})"
        )

    if mode is PolicyMode.GUARDED and tier >= Tier.STATEFUL:
        if allow:
            try:
                if re.search(allow, probe):
                    return PolicyDecision(
                        tier, True, "guarded: allowed by NOUS_POLICY_ALLOW"
                    )
            except re.error:
                return PolicyDecision(tier, False, "invalid NOUS_POLICY_ALLOW regex")
        return PolicyDecision(
            tier,
            False,
            f"guarded mode refuses Tier {int(tier)} ({tier.name}) without NOUS_POLICY_ALLOW match",
        )

    return PolicyDecision(tier, True, "permitted")
