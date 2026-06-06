"""Self-model situational awareness: one fused, controller-facing picture (BL-061).

``assess`` (ADR 0010) answers "what can the device do right now, and how
confident are you?" as three capability claims with calibrated quantile bands.
This layer fuses those claims with the rest of the tactical picture a controller
would otherwise assemble by hand from three separate reads: each claim's
provenance (the estimator behind it and how stale that estimate is), the FSM
posture (mode plus the operator and comms labels), the safety enforcer's
violation counts, and a short ranked list of degraded-mode recommendations.

``situation`` builds on ``assess`` rather than recomputing the quantile mapping,
so the headline numbers match ``self_model_assess`` exactly.

Two honesty notes shape the output. ``age_s`` is the estimator clock lag
measured against the freshest estimator clock (the max ``ts_s`` across the
estimators), not the engine clock: ``profile_reload`` rebuilds estimators on a
fresh timebase while the engine clock keeps counting, so an engine-clock
reference would report a constant false staleness after a reload. Against the
estimator timebase it sits near zero under live ticking and grows only when one
estimator lags the others, which is the case a controller must see. The live trust signal
stays the covariance-derived ``confidence`` carried on each claim; both are
surfaced so a stale claim is distinguishable from a merely uncertain one. The
recommendations are advisory heuristics, ranked to mirror the engine's own
auto-safing priority (operator, power, thermal, comms; ADR 0027, ADR 0028); they
are not a safety gate. The ``SafetyEnforcer`` (ADR 0022) remains the only
authority that refuses or clamps, and where the engine carries a real threshold
(thermal headroom) the status reads against it rather than inventing one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..state.comms_state import CommsState
from ..state.machine import Mode, is_impaired, is_terminal
from ..state.operator_state import OperatorState
from .assess import assess

if TYPE_CHECKING:
    from ..engine import Engine
    from ..types import Capability, Estimate

__all__ = [
    "CapabilitySituation",
    "DriverProvenance",
    "Posture",
    "Situation",
    "situation",
]


# Advisory status thresholds. These are NOT safety constraints (those live in
# the SafetyEnforcer, ADR 0022): they only colour the situational read so a
# controller sees "tight" before "violated". Tuned for the reference profile's
# scale; a deployment with a very different envelope may want them read from the
# profile (an ADR 0038 revisit trigger).
_LOW_CONFIDENCE = 0.5
_ENDURANCE_CRITICAL_MIN = 15.0
_ENDURANCE_DEGRADED_MIN = 60.0
_INFERENCE_FLOOR_TOK_S = 1.0

_LINK_MODES = frozenset({Mode.RELAY, Mode.C2})
_DEGRADED_STATUSES = frozenset({"degraded", "critical"})

# Capability driver name -> the engine attribute holding its estimator. The
# self-model capabilities name their drivers in subsystem terms (``power``,
# ``thermal``, ...); this resolves each to the estimator whose source and
# timestamp back the claim.
_ESTIMATOR_ATTRS: dict[str, str] = {
    "power": "power_est",
    "apu": "apu_est",
    "thermal": "thermal_est",
    "compute": "compute_est",
    "storage": "storage_est",
    "comms": "comms_est",
    "position": "position_est",
    "sensors": "sensors_est",
    "biometrics": "biometrics_est",
}


class DriverProvenance(BaseModel):
    """Where one capability driver's belief comes from, and how fresh it is."""

    source: str
    age_s: float


class CapabilitySituation(BaseModel):
    """A capability claim enriched with a status label and its provenance."""

    name: str
    point: float
    p5: float
    p50: float
    p95: float
    confidence: float
    units: str
    status: str
    provenance: list[DriverProvenance] = Field(default_factory=list)


class Posture(BaseModel):
    """The FSM posture plus the derived operator and comms labels."""

    mode: str
    operator_state: str
    operator_state_reason: str
    comms_state: str
    comms_state_reason: str
    summary: str


class Situation(BaseModel):
    """A single fused, controller-facing situational read."""

    tick: int
    ts_s: float
    posture: Posture
    capabilities: list[CapabilitySituation] = Field(default_factory=list)
    safety: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


def situation(engine: Engine, *, seed: int = 0) -> Situation:
    """Return the device's fused situational picture.

    Reuses :func:`assess` for the capability quantiles, then layers on
    provenance, staleness, the FSM posture, the safety posture, and a ranked set
    of degraded-mode recommendations.
    """
    a = assess("situation", engine=engine, seed=seed)
    states = _estimator_states(engine)
    # The staleness reference is the freshest estimator clock, not the engine
    # clock: profile_reload rebuilds estimators on a fresh timebase while the
    # engine clock keeps counting, so an engine-clock reference would report a
    # constant false staleness after a reload.
    now = max((s.ts_s for s in states.values()), default=float(engine.state.ts_s))
    caps: list[CapabilitySituation] = []
    by_name: dict[str, CapabilitySituation] = {}
    for cap in (a.endurance, a.thermal_headroom, a.inference_capacity):
        if cap is None:
            continue
        cs = _capability_situation(cap, engine, states, now)
        caps.append(cs)
        by_name[cs.name] = cs

    return Situation(
        tick=engine.state.tick,
        ts_s=round(float(engine.state.ts_s), 3),
        posture=_posture(engine, caps),
        capabilities=caps,
        safety=engine.safety.posture(),
        recommendations=_recommendations(engine, by_name),
    )


def _estimator_states(engine: Engine) -> dict[str, Estimate]:
    return {
        name: getattr(engine, attr).state()
        for name, attr in _ESTIMATOR_ATTRS.items()
    }


def _capability_situation(
    cap: Capability, engine: Engine, states: dict[str, Estimate], now: float
) -> CapabilitySituation:
    return CapabilitySituation(
        name=cap.name,
        point=cap.point,
        p5=cap.p5,
        p50=cap.p50,
        p95=cap.p95,
        confidence=cap.confidence,
        units=cap.units,
        status=_status(cap, engine),
        provenance=_provenance(cap, states, now),
    )


def _provenance(
    cap: Capability, states: dict[str, Estimate], now: float
) -> list[DriverProvenance]:
    out: list[DriverProvenance] = []
    for driver in cap.drivers:
        st = states.get(driver)
        if st is None:
            continue
        age = max(0.0, now - float(st.ts_s))
        out.append(DriverProvenance(source=st.source, age_s=round(age, 3)))
    return out


def _status(cap: Capability, engine: Engine) -> str:
    if cap.name == "thermal_headroom_c":
        return _thermal_status(cap, engine)
    if cap.name == "endurance_min":
        return _endurance_status(cap)
    if cap.name == "inference_capacity_tok_per_s":
        return _inference_status(cap, engine)
    return "nominal"


def _thermal_status(cap: Capability, engine: Engine) -> str:
    if engine.thermal.throttling or cap.p5 <= 0.0:
        return "critical"
    if cap.p5 < float(engine.thermal.headroom_threshold_c):
        return "degraded"
    if cap.confidence < _LOW_CONFIDENCE:
        return "watch"
    return "nominal"


def _endurance_status(cap: Capability) -> str:
    # assess reports confidence 0 only when the battery is net-charging, where
    # the endurance figure is a hint rather than a bound; that is not degraded.
    if cap.confidence == 0.0:
        return "nominal"
    if cap.p5 < _ENDURANCE_CRITICAL_MIN:
        return "critical"
    if cap.p5 < _ENDURANCE_DEGRADED_MIN:
        return "degraded"
    if cap.confidence < _LOW_CONFIDENCE:
        return "watch"
    return "nominal"


def _inference_status(cap: Capability, engine: Engine) -> str:
    if cap.point <= _INFERENCE_FLOOR_TOK_S:
        return "critical"
    if engine.compute.throttled:
        return "degraded"
    if cap.confidence < _LOW_CONFIDENCE:
        return "watch"
    return "nominal"


def _posture(engine: Engine, caps: list[CapabilitySituation]) -> Posture:
    mode = engine.state.mode
    operator = engine.state.operator_state
    comms = engine.state.comms_state
    return Posture(
        mode=mode.value,
        operator_state=operator.value,
        operator_state_reason=engine.state.operator_state_reason,
        comms_state=comms.value,
        comms_state_reason=engine.state.comms_state_reason,
        summary=_posture_summary(mode, operator, comms, caps),
    )


def _posture_summary(
    mode: Mode,
    operator: OperatorState,
    comms: CommsState,
    caps: list[CapabilitySituation],
) -> str:
    if is_terminal(mode):
        return "terminal"
    if mode is Mode.SAFE or is_impaired(mode):
        return "safed"
    if mode in (Mode.STOWED, Mode.BOOT):
        return "standby"
    degraded = (
        any(c.status in _DEGRADED_STATUSES for c in caps)
        or operator is OperatorState.INCAPACITATED
        or comms is CommsState.DENIED
    )
    return "degraded" if degraded else "nominal"


def _recommendations(
    engine: Engine, by_name: dict[str, CapabilitySituation]
) -> list[str]:
    """Ranked, advisory degraded-mode recommendations.

    Ordered to mirror the engine's auto-safing priority (ADR 0027, ADR 0028):
    operator, then power, then thermal, then comms, then the navigation and
    inference advisories. Each line names the observable that triggered it so the
    controller can act without a second read.
    """
    recs: list[str] = []
    state = engine.state

    if state.operator_state is OperatorState.INCAPACITATED:
        detail = state.operator_state_reason or "operator incapacitated"
        recs.append(
            f"operator: {detail}; hold a safe posture until the operator "
            "recovers (no supervisor for autonomous action)."
        )

    endurance = by_name.get("endurance_min")
    if endurance is not None and endurance.status in _DEGRADED_STATUSES:
        recs.append(
            f"power: endurance p5 is {endurance.p5:.0f} min; shed load or seek "
            "charge before committing to a long task."
        )

    thermal = by_name.get("thermal_headroom_c")
    if thermal is not None and thermal.status in _DEGRADED_STATUSES:
        if engine.thermal.throttling:
            recs.append(
                "thermal: the junction is at the throttle threshold; reduce "
                "inference load or hold in thermal_limit until it cools."
            )
        else:
            recs.append(
                f"thermal: junction headroom p5 is {thermal.p5:.1f} C; expect "
                "throttling under sustained load."
            )

    if state.comms_state is CommsState.DENIED:
        detail = state.comms_state_reason or "comms denied"
        if state.mode in _LINK_MODES:
            recs.append(
                f"comms: link denied in {state.mode.value} ({detail}); degrade "
                "to a non-link posture or restore a link before relying on "
                "relay/c2."
            )
        else:
            recs.append(
                f"comms: link denied ({detail}); off-board reporting is "
                "unavailable."
            )

    if not engine.position.has_fix:
        recs.append(
            "navigation: GNSS fix lost; the position estimate is dead-reckoned "
            "and will drift, do not rely on a nav-grade fix."
        )

    inference = by_name.get("inference_capacity_tok_per_s")
    if inference is not None and inference.status == "critical":
        recs.append(
            f"inference: local capacity is ~{inference.point:.0f} tok/s; defer "
            "or downsize local inference, or use the cloud path within the daily "
            "cap."
        )

    if not recs:
        recs.append("all monitored capabilities nominal; no action required.")
    return recs
