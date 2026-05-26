"""Unit tests for the BL-014 scenario layer."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from nous.engine import Engine
from nous.scenarios.injectors import apply_injection
from nous.scenarios.loader import load_scenario, load_scenario_file
from nous.scenarios.runner import run_scenario


@pytest.fixture
def engine(tmp_nous_home: Path) -> Engine:
    eng = Engine()
    eng.start()
    return eng


def test_loader_accepts_minimal_scenario() -> None:
    scenario = load_scenario({"meta": {"name": "smoke"}, "steps": []})
    assert scenario.name == "smoke"
    assert scenario.profile == "jetson-agx-orin"
    assert scenario.tick_budget >= 1


def test_loader_sorts_steps() -> None:
    scenario = load_scenario(
        {
            "steps": [
                {"at_min": 30, "action": "state_transition", "args": {"trigger": "shutdown"}},
                {"at_min": 0, "action": "state_transition", "args": {"trigger": "mission"}},
            ]
        }
    )
    sorted_steps = scenario.steps_sorted()
    assert sorted_steps[0].at_min == 0
    assert sorted_steps[1].at_min == 30


def test_loader_reads_existing_scenarios() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    yaml_path = repo_root / "scenarios" / "operator-heat-strain.yaml"
    scenario = load_scenario_file(yaml_path)
    assert scenario.name == "operator-heat-strain"
    assert any(step.action == "inject_biometrics" for step in scenario.steps)


def test_load_scenario_file_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_scenario_file(tmp_path / "nope.yaml")


def test_inject_biometrics_delta_shifts_truth(engine: Engine) -> None:
    baseline = engine.biometrics.core_temp_c
    outcome = apply_injection(
        engine, "inject_biometrics", {"core_temp_c_delta": 1.5}
    )
    assert outcome["applied"] is True
    assert engine.biometrics.core_temp_c == pytest.approx(baseline + 1.5)


def test_inject_thermal_shifts_ambient(engine: Engine) -> None:
    baseline = engine.sensors.temp_c
    outcome = apply_injection(
        engine, "inject_thermal", {"ambient_delta_c": 10.0}
    )
    assert outcome["applied"] is True
    assert engine.sensors.temp_c == pytest.approx(baseline + 10.0)
    assert engine.thermal.ambient_c == pytest.approx(baseline + 10.0)


def test_inject_comms_loss_disables_link(engine: Engine) -> None:
    link_id = next(iter(engine.comms.link_ids))
    outcome = apply_injection(
        engine, "inject_comms_loss", {"link_id": link_id, "loss_pct": 100.0}
    )
    assert outcome["applied"] is True
    link = engine.comms.link(link_id)
    assert link is not None and not link.is_live()


def test_inject_compute_steers_load(engine: Engine) -> None:
    outcome = apply_injection(engine, "inject_compute", {"load_pct": 75.0})
    assert outcome["applied"] is True
    assert engine.compute.load_pct >= 75.0 - 1e-6


def test_unknown_action_is_skipped(engine: Engine) -> None:
    outcome = apply_injection(engine, "no_such_action", {})
    assert outcome["applied"] is False
    assert "unknown" in outcome["error"]


def test_runner_fires_state_transition(tmp_path: Path, engine: Engine) -> None:
    engine.fsm.reset()
    engine.fsm.transition("boot")
    engine.fsm.transition("ready")
    scenario = load_scenario(
        {
            "meta": {"name": "mission-burst"},
            "tick_budget": 5,
            "steps": [
                {"at_min": 0, "action": "state_transition",
                 "args": {"trigger": "mission",
                          "context": {"thermal_headroom_c": 25.0,
                                      "thermal_headroom_threshold_c": 5.0}}},
            ],
        }
    )
    report = run_scenario(engine, scenario)
    assert report["steps_fired"] == 1
    fired = report["records"][0]
    assert fired["action"] == "state_transition"
    assert fired["applied"] is True


def test_runner_records_late_steps_as_skipped(engine: Engine) -> None:
    scenario = load_scenario(
        {
            "tick_budget": 2,
            "steps": [
                {"at_min": 60, "action": "state_transition", "args": {"trigger": "mission"}},
            ],
        }
    )
    report = run_scenario(engine, scenario)
    assert report["steps_fired"] == 0
    assert report["steps_skipped"] == 1
    assert "tick budget exhausted" in report["records"][0]["error"]


def test_runner_returns_snapshot(engine: Engine) -> None:
    scenario = load_scenario({"tick_budget": 2, "steps": []})
    report = run_scenario(engine, scenario)
    snapshot = report["snapshot"]
    assert "tick" in snapshot
    assert snapshot["tick"] >= 2


def test_runner_uses_relative_tick_budget(engine: Engine) -> None:
    """Runner must not short-circuit when the engine has already advanced."""
    for _ in range(100):
        engine.tick()
    pre_run_tick = engine.state.tick
    scenario = load_scenario({"tick_budget": 4, "steps": []})
    report = run_scenario(engine, scenario)
    assert report["ticks_run"] == 4
    assert engine.state.tick == pre_run_tick + 4


def test_runner_fires_zero_minute_step_immediately(engine: Engine) -> None:
    scenario = load_scenario(
        {
            "tick_budget": 2,
            "steps": [
                {"at_min": 0, "action": "inject_biometrics",
                 "args": {"core_temp_c_delta": 1.0}},
            ],
        }
    )
    pre_run_tick = engine.state.tick
    report = run_scenario(engine, scenario)
    fired = report["records"][0]
    assert fired["applied"] is True
    assert fired["tick"] == pre_run_tick


def test_inject_sensor_drift_accepts_mps_args(engine: Engine) -> None:
    outcome = apply_injection(
        engine,
        "inject_sensor_drift",
        {"source": "position", "north_mps": 0.5, "east_mps": -0.2},
    )
    assert outcome["applied"] is True
    assert outcome["result"]["north_mps"] == 0.5
    assert outcome["result"]["east_mps"] == -0.2


def test_inject_sensor_drift_legacy_alias(engine: Engine) -> None:
    """Legacy ``lat_bias_m`` alias still routes to set_imu_drift."""
    outcome = apply_injection(
        engine,
        "inject_sensor_drift",
        {"source": "position", "lat_bias_m": 0.1},
    )
    assert outcome["applied"] is True
    assert outcome["result"]["north_mps"] == 0.1


def test_steps_sorted_preserves_declaration_order_for_same_at_min() -> None:
    scenario = load_scenario(
        {
            "steps": [
                {"at_min": 5, "action": "inject_thermal",
                 "args": {"ambient_delta_c": 1.0}},
                {"at_min": 5, "action": "state_transition",
                 "args": {"trigger": "degrade"}},
                {"at_min": 5, "action": "inject_biometrics",
                 "args": {"core_temp_c_delta": 0.5}},
            ],
        }
    )
    ordered = scenario.steps_sorted()
    assert [s.action for s in ordered] == [
        "inject_thermal",
        "state_transition",
        "inject_biometrics",
    ]


def test_state_transition_denied_marked_not_applied(engine: Engine) -> None:
    outcome = apply_injection(
        engine,
        "state_transition",
        {"trigger": "no_such_trigger"},
    )
    assert outcome["applied"] is False
    assert outcome["error"]


def test_inline_yaml_round_trip(tmp_path: Path, engine: Engine) -> None:
    yaml_text = dedent(
        """
        schema_version: "0.1.0"
        meta: { name: round-trip }
        tick_budget: 3
        steps:
          - { at_min: 0, action: inject_biometrics, args: { core_temp_c_delta: 0.5 } }
        """
    )
    path = tmp_path / "round_trip.yaml"
    path.write_text(yaml_text)
    scenario = load_scenario_file(path)
    report = run_scenario(engine, scenario)
    assert report["steps_fired"] == 1
