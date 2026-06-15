"""Self-model and estimator tools (ADR 0021, ADR 0041).

The self-model capability assessment, the task-viability check, the
estimator-status read, and the fused situational read (all T0), plus the
T2 ``self_model_publish`` mutator that pushes the current self-model read
through an interop adapter onto a comms link (ADR 0041).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..engine import Engine
    from ..self_model.assess import Assessment
    from ..server import Nous, WrapFn


# Adapters with an envelope the self-model read can ride (ADR 0041). The
# registry's pure position codecs (nmea0183, misb_klv) are not here, so they
# are refused before the read is even computed.
_SHAPED_ADAPTERS = frozenset({"mqtt", "sensorthings", "stanag_4774", "cot"})


def _assess_payload(a: Assessment) -> dict[str, Any]:
    """The ``self_model_assess`` response body; shared with the publish tool."""
    from ..self_model.explain import explain

    return {
        "question": a.question,
        "capabilities": {
            cap.name: cap.model_dump()
            for cap in (a.endurance, a.thermal_headroom, a.inference_capacity)
            if cap is not None
        },
        "explanation": explain(a),
    }


def _publish_shape(
    adapter: str, kind: str, body: Mapping[str, Any], *, engine: Engine
) -> dict[str, Any] | None:
    """Shape the self-model read into the named adapter's idiomatic input.

    Each adapter consumes a different envelope: MQTT takes the whole
    mapping, SensorThings carries it as the Observation ``result``, STANAG
    4774 wraps it as the labelled ``payload``, and CoT carries the device's
    estimated position with a one-line summary in ``remarks``. The pure
    position codecs (``nmea0183``, ``misb_klv``) have no generic payload
    channel, so they return ``None`` and the tool refuses. The simulated
    clock stays nested below the top level so the SC-4 freshness gate
    (``resolve_ts``) reads the wall clock of this live read, not a
    sim-epoch offset.
    """
    tag = f"self_model_{kind}"
    name = adapter.strip().lower()
    if name == "mqtt":
        return {"kind": tag, "self_model": dict(body)}
    if name == "sensorthings":
        return {"datastream": f"nous-{tag}", "result": dict(body)}
    if name == "stanag_4774":
        return {"payload": {"kind": tag, "self_model": dict(body)}}
    if name == "cot":
        est = engine.position_est.state()
        return {
            "uid": "nous-self-model",
            "lat": est.point.get("lat", 0.0),
            "lon": est.point.get("lon", 0.0),
            "hae": est.point.get("alt_m", 0.0),
            "remarks": _cot_remarks(kind, body),
        }
    return None


def _cot_remarks(kind: str, body: Mapping[str, Any]) -> str:
    """One-line capability summary for the CoT ``<remarks>`` detail."""
    if kind == "assess":
        return str(body.get("explanation", ""))
    posture = body.get("posture")
    summary = str(posture.get("summary", "")) if isinstance(posture, Mapping) else ""
    caps = "; ".join(
        f"{c['name']}={c['p50']:.1f}{c['units']} ({c['status']})"
        for c in body.get("capabilities", [])
        if isinstance(c, Mapping)
    )
    return f"{summary}; {caps}" if summary and caps else summary or caps


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the self-model and estimator tools on ``mcp``."""

    @mcp.tool()
    async def self_model_assess(question: str = "", ctx: Context | None = None) -> str:
        """Self-model capability assessment with calibrated p5/p50/p95 bands."""

        async def _work() -> str:
            from ..self_model.assess import assess

            return json.dumps(_assess_payload(assess(question, engine=app.engine)))

        return await wrap(
            "self_model_assess", {"question": question}, ctx, _work
        )

    @mcp.tool()
    async def self_model_viability(
        task: str,
        endurance_min: float | None = None,
        thermal_headroom_c: float | None = None,
        inference_tok_per_s: float | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Decide whether a task is feasible against the current capabilities."""

        async def _work() -> str:
            from ..self_model.assess import assess
            from ..self_model.viability import viability

            requirements: dict[str, float] = {}
            if endurance_min is not None:
                requirements["endurance_min"] = float(endurance_min)
            if thermal_headroom_c is not None:
                requirements["thermal_headroom_c"] = float(thermal_headroom_c)
            if inference_tok_per_s is not None:
                requirements["inference_tok_per_s"] = float(inference_tok_per_s)

            a = assess(task, engine=app.engine)
            v = viability(a, task, requirements=requirements or None)
            return json.dumps(
                {
                    "task": task,
                    "feasible": v.feasible,
                    "confidence": v.confidence,
                    "reason": v.reason,
                    "requirements": requirements,
                }
            )

        return await wrap(
            "self_model_viability",
            {
                "task": task,
                "endurance_min": endurance_min,
                "thermal_headroom_c": thermal_headroom_c,
                "inference_tok_per_s": inference_tok_per_s,
            },
            ctx,
            _work,
        )

    @mcp.tool()
    async def self_estimator_status(ctx: Context | None = None) -> str:
        """Estimator means, covariances, and per-filter health.

        Each row carries the filtered ``point`` and ``covariance`` plus a
        ``health`` block (ADR 0045): ``healthy`` and ``fused`` flags, the
        ``rejected_updates`` and ``reset_count`` totals, a ``dead_reckoning``
        flag for a filter coasting without an accepted measurement, and the
        per-channel innovation ``test_ratio`` (a value above 1 means the last
        reading fell outside the gate) and its signed, smoothed
        ``test_ratio_filtered``.
        """

        async def _work() -> str:
            rows = []
            for est in (
                app.engine.power_est,
                app.engine.apu_est,
                app.engine.thermal_est,
                app.engine.compute_est,
                app.engine.storage_est,
                app.engine.comms_est,
                app.engine.position_est,
                app.engine.sensors_est,
                app.engine.biometrics_est,
            ):
                state = est.state()
                rows.append(
                    {
                        "source": state.source,
                        "ts_s": round(state.ts_s, 3),
                        "point": {k: round(v, 4) for k, v in state.point.items()},
                        "covariance": {
                            k: round(float(v), 6) for k, v in state.covariance.items()
                        },
                        "health": (
                            state.health.model_dump()
                            if state.health is not None
                            else None
                        ),
                    }
                )
            return json.dumps({"estimators": rows})

        return await wrap("self_estimator_status", {}, ctx, _work)

    @mcp.tool()
    async def self_model_situation(ctx: Context | None = None) -> str:
        """Fused situational read: capabilities, provenance, posture, safety, recommendations."""

        async def _work() -> str:
            from ..self_model.situation import situation

            return json.dumps(situation(app.engine).model_dump())

        return await wrap("self_model_situation", {}, ctx, _work)

    @mcp.tool()
    async def self_model_publish(
        link_id: str,
        adapter: str = "mqtt",
        kind: str = "situation",
        ctx: Context | None = None,
    ) -> str:
        """Publish the current self-model read over a comms link (T2, ADR 0041).

        Composes the self-model with the interop registry and the comms
        ``tx`` seam, the same publish path as ``comms_publish``: the read is
        shaped for the named adapter, encoded to wire bytes, and those bytes
        are accounted against the link's envelope (age reset, throughput
        updated). ``kind`` selects the read: ``situation`` (the fused
        ``self_model_situation`` payload) or ``assess`` (the
        ``self_model_assess`` payload). Adapters with a generic payload
        channel (``mqtt``, ``sensorthings``, ``stanag_4774``) carry the full
        read; ``cot`` emits a position event with a one-line capability
        summary in its remarks; the pure position codecs (``nmea0183``,
        ``misb_klv``) are refused. Encode errors and unknown adapters are
        reported as ``{"ok": false, ...}``; nothing is transmitted on a
        failure. Tier T2 (stateful): the link's live state changes.
        """

        async def _work() -> str:
            from ..interop import REGISTRY
            from ..self_model.assess import assess
            from ..self_model.situation import situation
            from .publish import encode_and_tx

            if kind not in ("situation", "assess"):
                return json.dumps(
                    {
                        "ok": False,
                        "error": (
                            f"unknown kind {kind!r}; expected 'situation' or 'assess'"
                        ),
                    }
                )
            name = adapter.strip().lower()
            if name in REGISTRY and name not in _SHAPED_ADAPTERS:
                return json.dumps(
                    {
                        "ok": False,
                        "adapter": adapter,
                        "error": (
                            "adapter has no payload channel for a self-model "
                            "read; use mqtt, sensorthings, stanag_4774, or cot"
                        ),
                    }
                )

            body: dict[str, Any]
            if kind == "situation":
                body = situation(app.engine).model_dump()
            else:
                body = _assess_payload(assess("publish", engine=app.engine))
            from ._errors import error_class

            try:
                data = _publish_shape(name, kind, body, engine=app.engine)
            except (ValueError, TypeError) as exc:
                return json.dumps(
                    {"ok": False, "adapter": adapter, "error": error_class(exc)}
                )
            if data is None:
                # Only an unregistered name reaches here (shaped and
                # position-codec names were dispatched above); delegate to
                # the helper for the canonical unknown-adapter error.
                data = {}
            return json.dumps(
                encode_and_tx(
                    app.engine, link_id, adapter, data, extra={"kind": kind}
                )
            )

        return await wrap(
            "self_model_publish",
            {"link_id": link_id, "adapter": adapter, "kind": kind},
            ctx,
            _work,
        )
