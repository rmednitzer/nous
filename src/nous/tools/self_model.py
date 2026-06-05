"""Self-model and estimator tools (ADR 0021).

The self-model capability assessment, the task-viability check, and the
estimator-status read (all T0), extracted from ``server.py``. Handler bodies
and docstrings are byte-faithful to the inline definitions they replace, so the
registered tool surface does not change.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..server import Nous, WrapFn


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the self-model and estimator tools on ``mcp``."""

    @mcp.tool()
    async def self_model_assess(question: str = "", ctx: Context | None = None) -> str:
        """Self-model capability assessment with calibrated p5/p50/p95 bands."""

        async def _work() -> str:
            from ..self_model.assess import assess
            from ..self_model.explain import explain

            a = assess(question, engine=app.engine)
            payload = {
                "question": a.question,
                "capabilities": {
                    cap.name: cap.model_dump()
                    for cap in (
                        a.endurance,
                        a.thermal_headroom,
                        a.inference_capacity,
                    )
                    if cap is not None
                },
                "explanation": explain(a),
            }
            return json.dumps(payload)

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
        """Estimator covariances, last update times, divergence flags."""

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
                    }
                )
            return json.dumps({"estimators": rows})

        return await wrap("self_estimator_status", {}, ctx, _work)
