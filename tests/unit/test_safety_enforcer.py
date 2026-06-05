"""Unit tests for the ADR 0022 runtime safety enforcer foundation.

The enforcer is a safety seam: a bug that approves a candidate it should
refuse defeats the constraint. These tests pin the structured result, the
fail-closed posture of both evaluators, the violation counters, and the
SC-2-shaped floor check the FSM guard will route through when the wiring PR
lands.
"""

from __future__ import annotations

import dataclasses

import pytest
from hypothesis import given
from hypothesis import strategies as st

from nous.safety import (
    CLAMPED,
    REFUSED,
    UNREGISTERED,
    SafetyEnforcer,
    SafetyResult,
    ceiling_clamp,
    floor_threshold,
)

_finite = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)


def test_safety_result_defaults() -> None:
    result = SafetyResult(approved=True, value=42)
    assert result.was_clamped is False
    assert result.constraint_id == ""
    assert result.violation_type is None
    assert result.evidence == {}


def test_safety_result_is_frozen() -> None:
    result = SafetyResult(approved=True, value=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.approved = False  # type: ignore[misc]


def test_floor_threshold_approves_at_and_above() -> None:
    evaluator = floor_threshold("t")
    at = evaluator(5.0, {"t": 5.0})
    above = evaluator(9.0, {"t": 5.0})
    assert at.approved and above.approved
    assert at.violation_type is None
    assert above.value == 9.0


def test_floor_threshold_refuses_below() -> None:
    evaluator = floor_threshold("threshold_c", label="thermal headroom", unit="C")
    result = evaluator(3.0, {"threshold_c": 5.0})
    assert not result.approved
    assert result.violation_type == REFUSED
    assert "thermal headroom" in str(result.evidence["detail"])
    assert "below threshold" in str(result.evidence["detail"])


@pytest.mark.parametrize(
    ("candidate", "evidence"),
    [
        (None, {"t": 5.0}),
        (5.0, {}),
        ("warm", {"t": 5.0}),
        (5.0, {"t": "cold"}),
        (float("nan"), {"t": 5.0}),
        (5.0, {"t": float("nan")}),
        (float("inf"), {"t": 5.0}),
        (float("-inf"), {"t": 5.0}),
        (5.0, {"t": float("inf")}),
    ],
)
def test_floor_threshold_fails_closed(candidate: object, evidence: dict[str, object]) -> None:
    result = floor_threshold("t")(candidate, evidence)
    assert not result.approved
    assert result.violation_type == REFUSED


def test_ceiling_clamp_passes_under_ceiling() -> None:
    result = ceiling_clamp("cap")(40.0, {"cap": 60.0})
    assert result.approved
    assert result.was_clamped is False
    assert result.value == 40.0
    assert result.violation_type is None


def test_ceiling_clamp_clamps_over_ceiling() -> None:
    result = ceiling_clamp("cap", label="load", unit="W")(90.0, {"cap": 60.0})
    assert result.approved
    assert result.was_clamped is True
    assert result.value == 60.0
    assert result.violation_type == CLAMPED
    assert "clamped to" in str(result.evidence["detail"])


@pytest.mark.parametrize(
    ("candidate", "evidence"),
    [
        (90.0, {}),
        (None, {"cap": 60.0}),
        ("hot", {"cap": 60.0}),
        (90.0, {"cap": "warm"}),
        (float("inf"), {"cap": 60.0}),
        (40.0, {"cap": float("inf")}),
        (float("nan"), {"cap": 60.0}),
    ],
)
def test_ceiling_clamp_fails_closed(candidate: object, evidence: dict[str, object]) -> None:
    result = ceiling_clamp("cap")(candidate, evidence)
    assert not result.approved
    assert result.violation_type == REFUSED


def test_evaluators_return_finite_float_value_for_numeric_string() -> None:
    floored = floor_threshold("t")("9.0", {"t": 5.0})
    assert floored.approved
    assert isinstance(floored.value, float)
    assert floored.value == 9.0

    passed = ceiling_clamp("cap")("40.0", {"cap": 60.0})
    assert passed.approved
    assert isinstance(passed.value, float)
    assert passed.value == 40.0


def test_enforcer_stamps_constraint_id() -> None:
    enforcer = SafetyEnforcer()
    enforcer.register("SC-2", floor_threshold("threshold_c"))
    result = enforcer.check("SC-2", 9.0, evidence={"threshold_c": 5.0})
    assert result.approved
    assert result.constraint_id == "SC-2"


def test_enforcer_unregistered_constraint_fails_closed() -> None:
    enforcer = SafetyEnforcer()
    result = enforcer.check("SC-99", 1.0, evidence={"anything": 1})
    assert not result.approved
    assert result.violation_type == UNREGISTERED
    assert enforcer.violation_count("SC-99") == 1


def test_enforcer_counts_refusals_and_clamps_but_not_passes() -> None:
    enforcer = SafetyEnforcer()
    enforcer.register("SC-2", floor_threshold("threshold_c"))
    enforcer.register("THROTTLE", ceiling_clamp("cap"))

    enforcer.check("SC-2", 9.0, evidence={"threshold_c": 5.0})  # pass
    enforcer.check("SC-2", 1.0, evidence={"threshold_c": 5.0})  # refuse
    enforcer.check("THROTTLE", 40.0, evidence={"cap": 60.0})  # pass
    enforcer.check("THROTTLE", 90.0, evidence={"cap": 60.0})  # clamp

    assert enforcer.violation_count("SC-2") == 1
    assert enforcer.violation_count("THROTTLE") == 1
    assert enforcer.total_violations == 2


def test_enforcer_posture_shape() -> None:
    enforcer = SafetyEnforcer()
    enforcer.register("SC-2", floor_threshold("threshold_c"))
    enforcer.check("SC-2", 1.0, evidence={"threshold_c": 5.0})
    posture = enforcer.posture()
    assert posture["total_violations"] == 1
    assert posture["by_constraint"] == {"SC-2": 1}
    assert posture["registered"] == ["SC-2"]


def test_reason_prefixes_constraint_id_and_carries_detail() -> None:
    enforcer = SafetyEnforcer()
    enforcer.register("SC-2", floor_threshold("threshold_c", label="thermal headroom"))
    result = enforcer.check("SC-2", 1.0, evidence={"threshold_c": 5.0})
    assert result.reason.startswith("SC-2: ")
    assert "thermal headroom" in result.reason


def test_evaluator_preserves_caller_evidence() -> None:
    result = floor_threshold("t")(1.0, {"t": 5.0, "source": "thermal_est"})
    assert result.evidence["source"] == "thermal_est"
    assert "detail" in result.evidence


@given(candidate=_finite, threshold=_finite)
def test_floor_threshold_approves_iff_at_or_above(
    candidate: float, threshold: float
) -> None:
    result = floor_threshold("t")(candidate, {"t": threshold})
    assert result.approved == (candidate >= threshold)
    assert isinstance(result.reason, str)


@given(candidate=_finite, ceiling=_finite)
def test_ceiling_clamp_never_exceeds_ceiling(candidate: float, ceiling: float) -> None:
    result = ceiling_clamp("cap")(candidate, {"cap": ceiling})
    assert result.approved
    assert float(result.value) <= ceiling
    assert result.was_clamped == (candidate > ceiling)
