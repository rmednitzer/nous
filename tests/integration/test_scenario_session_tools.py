"""Scenario session control through the registered tool surface (ADR 0040).

``scenario_load(mode="session")`` starts a timeline riding the live tick
stream; ``scenario_status`` / ``scenario_pause`` / ``scenario_resume`` /
``scenario_reset`` were classified from L0 (ADR 0007) and register once the
stateful runner exists. ``build_app`` does not run the tick loop, so these
tests drive time with the ``tick_advance`` tool exactly as a controller on
the stateless HTTP transport would.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nous.config import Settings
from nous.server import build_app


def _payload(result: Any) -> dict[str, Any]:
    content, _structured = result
    data: dict[str, Any] = json.loads(content[0].text)
    return data


def _write_scenario(tmp_path: Path, *, tick_budget: int = 6) -> str:
    path = tmp_path / "session-scenario.yaml"
    path.write_text(
        "\n".join(
            [
                "meta:",
                "  name: tool-session",
                f"tick_budget: {tick_budget}",
                "steps:",
                "  - { at_min: 0, action: inject_compute, args: { load_pct: 20 } }",
                "  - { at_min: 0.025, action: inject_compute, args: { load_pct: 75 } }",
            ]
        ),
        encoding="utf-8",
    )
    return str(path)


async def test_session_lifecycle_through_tools(
    config: Settings, tmp_path: Path
) -> None:
    app = build_app(config)
    path = _write_scenario(tmp_path)

    loaded = _payload(
        await app.mcp.call_tool("scenario_load", {"path": path, "mode": "session"})
    )
    assert loaded["ok"] is True
    assert loaded["mode"] == "session"
    # The t=0 step fired at the load boundary; the call returned immediately.
    assert loaded["session"]["state"] == "running"
    assert loaded["session"]["steps_fired"] == 1
    assert loaded["session"]["ticks_run"] == 0

    status = _payload(await app.mcp.call_tool("scenario_status", {}))
    assert status["active"] is True
    assert status["steps_pending"] == 1

    # Two ticks: not enough for the 0.025 min step (3 ticks at 2 Hz).
    _payload(await app.mcp.call_tool("tick_advance", {"n": 2}))
    status = _payload(await app.mcp.call_tool("scenario_status", {}))
    assert status["steps_fired"] == 1

    paused = _payload(await app.mcp.call_tool("scenario_pause", {}))
    assert paused["ok"] is True and paused["state"] == "paused"

    # The device ticks on; the frozen scenario clock consumes nothing.
    _payload(await app.mcp.call_tool("tick_advance", {"n": 4}))
    status = _payload(await app.mcp.call_tool("scenario_status", {}))
    assert status["ticks_run"] == 2
    assert status["steps_fired"] == 1

    resumed = _payload(await app.mcp.call_tool("scenario_resume", {}))
    assert resumed["ok"] is True and resumed["state"] == "running"

    # Four more scenario ticks cross the second step and exhaust the budget.
    _payload(await app.mcp.call_tool("tick_advance", {"n": 4}))
    status = _payload(await app.mcp.call_tool("scenario_status", {}))
    assert status["state"] == "done"
    assert status["active"] is False
    assert status["steps_fired"] == 2
    assert status["steps_pending"] == 0
    assert "snapshot" in status

    reset = _payload(await app.mcp.call_tool("scenario_reset", {}))
    assert reset["ok"] is True and reset["cleared"] is True
    assert reset["state_at_reset"] == "done"
    assert _payload(await app.mcp.call_tool("scenario_status", {})) == {
        "active": False
    }


async def test_second_load_refused_while_session_active(
    config: Settings, tmp_path: Path
) -> None:
    app = build_app(config)
    path = _write_scenario(tmp_path, tick_budget=600)

    first = _payload(
        await app.mcp.call_tool("scenario_load", {"path": path, "mode": "session"})
    )
    assert first["ok"] is True

    for mode in ("session", "run"):
        again = _payload(
            await app.mcp.call_tool("scenario_load", {"path": path, "mode": mode})
        )
        assert again["ok"] is False
        assert "already active" in again["error"]
        assert "records" not in again["session"]

    _payload(await app.mcp.call_tool("scenario_reset", {}))
    fresh = _payload(
        await app.mcp.call_tool("scenario_load", {"path": path, "mode": "session"})
    )
    assert fresh["ok"] is True


async def test_done_session_snapshot_is_frozen_at_completion(
    config: Settings, tmp_path: Path
) -> None:
    app = build_app(config)
    path = _write_scenario(tmp_path)

    _payload(await app.mcp.call_tool("scenario_load", {"path": path, "mode": "session"}))
    _payload(await app.mcp.call_tool("tick_advance", {"n": 6}))
    done = _payload(await app.mcp.call_tool("scenario_status", {}))
    assert done["state"] == "done"
    completion_tick = done["snapshot"]["tick"]

    # The engine keeps living after the scenario ends; the report must not.
    _payload(await app.mcp.call_tool("tick_advance", {"n": 10}))
    later = _payload(await app.mcp.call_tool("scenario_status", {}))
    assert later["snapshot"]["tick"] == completion_tick
    assert app.engine.state.tick == completion_tick + 10


async def test_next_load_clears_a_finished_session(
    config: Settings, tmp_path: Path
) -> None:
    app = build_app(config)
    path = _write_scenario(tmp_path)

    _payload(await app.mcp.call_tool("scenario_load", {"path": path, "mode": "session"}))
    _payload(await app.mcp.call_tool("tick_advance", {"n": 6}))
    assert _payload(await app.mcp.call_tool("scenario_status", {}))["state"] == "done"

    # A finished session does not block a one-shot run, and it must not
    # linger: status afterwards reports no session rather than the stale
    # one against an engine that has moved on.
    report = _payload(await app.mcp.call_tool("scenario_load", {"path": path}))
    assert report["steps_total"] == 2
    assert _payload(await app.mcp.call_tool("scenario_status", {})) == {
        "active": False
    }


async def test_unknown_mode_is_refused(config: Settings, tmp_path: Path) -> None:
    app = build_app(config)
    path = _write_scenario(tmp_path)

    out = _payload(
        await app.mcp.call_tool("scenario_load", {"path": path, "mode": "warp"})
    )
    assert out["ok"] is False
    assert "unknown mode" in out["error"]
    assert app.scenario_session is None


async def test_run_mode_report_shape_is_unchanged(
    config: Settings, tmp_path: Path
) -> None:
    app = build_app(config)
    path = _write_scenario(tmp_path)

    report = _payload(await app.mcp.call_tool("scenario_load", {"path": path}))
    # The historical one-shot contract: a report, not an ok/session envelope.
    assert report["name"] == "tool-session"
    assert report["steps_total"] == 2
    assert report["steps_fired"] == 2
    assert report["ticks_run"] == 6
    assert "snapshot" in report


async def test_control_verbs_without_a_session(config: Settings) -> None:
    app = build_app(config)

    assert _payload(await app.mcp.call_tool("scenario_status", {})) == {
        "active": False
    }
    pause = _payload(await app.mcp.call_tool("scenario_pause", {}))
    assert pause["ok"] is False and "no scenario session" in pause["error"]
    resume = _payload(await app.mcp.call_tool("scenario_resume", {}))
    assert resume["ok"] is False and "no scenario session" in resume["error"]
    reset = _payload(await app.mcp.call_tool("scenario_reset", {}))
    assert reset == {"ok": True, "cleared": False}
