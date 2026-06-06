"""Regenerate the showcase scenario gallery.

Runs each ``scenarios/*.yaml`` through ``Engine.tick()`` and writes one
JSONL telemetry trace and one summary markdown page per scenario. Steps
are applied through the BL-014 injector dispatch
(:func:`nous.scenarios.injectors.apply_injection`), the same path the
``scenario_load`` / ``scenario_inject`` tools use, so the gallery reflects
the live runner; an injector that refuses or errors is recorded as a
``skipped`` annotation rather than silently dropped. ADR 0017 defines the
showcase site this generator feeds.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_DIR = REPO_ROOT / "scenarios"
SHOWCASE_DIR = REPO_ROOT / "docs" / "showcase"
DATA_DIR = SHOWCASE_DIR / "data"
GALLERY_DIR = SHOWCASE_DIR / "scenarios"

SAMPLE_EVERY_TICKS = 12
SPARKLINE_BUCKETS = 48
SPARKLINE_CHARS = "_.-=+*#%@"

SHOWCASE_TICK_HZ = 1.0 / 60.0


def _load_engine_module() -> Any:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from nous.engine import Engine

    return Engine


def _sparkline(values: list[float]) -> str:
    if not values:
        return ""
    lo = min(values)
    hi = max(values)
    if hi - lo < 1e-9:
        return SPARKLINE_CHARS[len(SPARKLINE_CHARS) // 2] * len(values)
    span = hi - lo
    bucket_count = len(SPARKLINE_CHARS) - 1
    return "".join(
        SPARKLINE_CHARS[round((v - lo) / span * bucket_count)] for v in values
    )


def _resample(values: list[float], buckets: int) -> list[float]:
    if not values:
        return []
    if len(values) <= buckets:
        return values
    step = len(values) / buckets
    return [values[min(len(values) - 1, int(i * step))] for i in range(buckets)]


def _apply_step(engine: Any, action: str, args: Mapping[str, Any]) -> str:
    from nous.scenarios.injectors import apply_injection

    outcome = apply_injection(engine, action, dict(args))
    if not outcome["applied"]:
        return f"skipped: {outcome.get('error', 'not applied')}"
    result = outcome.get("result")
    if action == "state_transition" and isinstance(result, Mapping):
        return f"applied: mode -> {result.get('mode')}"
    if isinstance(result, Mapping) and result:
        changes = ", ".join(f"{k}={v}" for k, v in result.items())
        return f"applied: {changes}"
    return "applied"


def _ticks_per_minute(engine: Any) -> float:
    return 60.0 * float(engine.settings.tick_hz)


def _load_scenario(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


def _scenario_meta(doc: Mapping[str, Any]) -> dict[str, Any]:
    meta = doc.get("meta") or {}
    if not isinstance(meta, Mapping):
        return {}
    return dict(meta)


def _run_scenario(engine_cls: Any, path: Path) -> dict[str, Any]:
    doc = _load_scenario(path)
    meta = _scenario_meta(doc)
    profile = doc.get("profile") or "jetson-agx-orin"
    tick_budget = int(doc.get("tick_budget") or 600)
    steps = doc.get("steps") or []

    from nous.config import Settings

    engine = engine_cls(
        settings=Settings(profile=str(profile), tick_hz=SHOWCASE_TICK_HZ)
    )
    engine.start()
    if engine.fsm.can("ready"):
        engine.state.mode = engine.fsm.transition("ready")

    tpm = _ticks_per_minute(engine)
    step_ticks = {
        max(1, round(float(step.get("at_min", 0)) * tpm)): step
        for step in steps
        if isinstance(step, Mapping)
    }

    samples: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []

    for tick_n in range(1, tick_budget + 1):
        if tick_n in step_ticks:
            step = step_ticks[tick_n]
            outcome = _apply_step(
                engine,
                str(step.get("action", "")),
                step.get("args") or {},
            )
            timeline.append(
                {
                    "tick": tick_n,
                    "at_min": float(step.get("at_min", 0)),
                    "action": step.get("action"),
                    "args": dict(step.get("args") or {}),
                    "outcome": outcome,
                }
            )
        engine.tick()
        if tick_n == 1 or tick_n == tick_budget or tick_n % SAMPLE_EVERY_TICKS == 0:
            snap = engine.snapshot()
            samples.append(snap)

    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "meta": meta,
        "profile": profile,
        "tick_budget": tick_budget,
        "tick_hz": float(engine.settings.tick_hz),
        "samples": samples,
        "timeline": timeline,
    }


def _write_jsonl(target: Path, trace: Mapping[str, Any]) -> None:
    header = {k: v for k, v in trace.items() if k not in ("samples", "timeline")}
    lines: list[str] = [json.dumps({"kind": "header", **header}, sort_keys=True)]
    for event in trace["timeline"]:
        lines.append(json.dumps({"kind": "event", **event}, sort_keys=True))
    for sample in trace["samples"]:
        lines.append(json.dumps({"kind": "sample", **sample}, sort_keys=True))
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_summary_md(name: str, trace: Mapping[str, Any]) -> str:
    samples = trace["samples"]
    soc = [float(s["power"]["soc_pct"]) for s in samples]
    apu_w = [float(s["apu"]["total_w"]) for s in samples]

    soc_spark = _sparkline(_resample(soc, SPARKLINE_BUCKETS))
    apu_spark = _sparkline(_resample(apu_w, SPARKLINE_BUCKETS))
    final = samples[-1] if samples else {}

    def fmt_meta_row(key: str) -> str:
        value = trace["meta"].get(key) or ""
        return f"| {key} | {value} |"

    lines: list[str] = []
    title = trace["meta"].get("name") or name
    lines.append(f"# Scenario: {title}")
    lines.append("")
    description = trace["meta"].get("description")
    if description:
        lines.append(str(description))
        lines.append("")
    lines.append("## Run metadata")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| profile | `{trace['profile']}` |")
    lines.append(f"| tick budget | {trace['tick_budget']} |")
    lines.append(f"| tick rate | {trace['tick_hz']:g} Hz |")
    lines.append(fmt_meta_row("name"))
    lines.append(f"| source | `{trace['path']}` |")
    lines.append("")
    lines.append("## Fidelity")
    lines.append("")
    lines.append("This run exercises the development-line subsystems and records the")
    lines.append("rest as defaults. See [Fidelity](../fidelity.md) for the legend.")
    lines.append("")
    lines.append("| Subsystem | Substance | Source |")
    lines.append("| --- | --- | --- |")
    lines.append("| power | `filtered` | Li-ion + Peukert + SoC Kalman |")
    lines.append(
        "| apu | `filtered` | solar MPPT, fuel cell, vehicle, "
        "USB-C PD; per-source Kalman |"
    )
    lines.append("| thermal | `filtered` | two-state lumped model; per-channel Kalman |")
    lines.append(
        "| compute | `filtered` | load fraction + profile-driven draw curve; "
        "per-channel Kalman |"
    )
    lines.append(
        "| storage | `filtered` | NAND wear + capacity accounting; per-channel Kalman |"
    )
    lines.append(
        "| sensors | `filtered` | temp / humidity / baro authoritative ambient; "
        "multi-channel Kalman |"
    )
    lines.append(
        "| position | `parametric` | dead reckoning + GNSS fix gating; "
        "Kalman passthrough (IMU fusion is BL-061) |"
    )
    lines.append(
        "| biometrics | `filtered` | HR / core temp / hydration / cognitive "
        "load with multi-channel Kalman |"
    )
    lines.append(
        "| comms | `parametric` | per-link envelopes drive FSM each tick; "
        "particle filter is BL-030 |"
    )
    lines.append(
        "| inference | `parametric` | local-path with profile-derived "
        "latency / energy / capacity |"
    )
    lines.append("")
    lines.append("## Final state")
    lines.append("")
    if final:
        lines.append(f"- mode: `{final.get('mode')}`")
        lines.append(f"- operator: `{final.get('operator_state')}`")
        lines.append(f"- comms: `{final.get('comms_state')}`")
        lines.append(f"- SoC: {final.get('power', {}).get('soc_pct')} %")
        lines.append(f"- APU offered: {final.get('apu', {}).get('total_w')} W")
        lines.append(f"- fuel: {final.get('apu', {}).get('fuel_pct')} %")
    lines.append("")
    lines.append("## Series")
    lines.append("")
    lines.append("Sparklines are over resampled buckets; high to the right is high value.")
    lines.append("")
    lines.append(f"- battery SoC: `{soc_spark}`")
    lines.append(f"- APU offered (W): `{apu_spark}`")
    lines.append("")
    lines.append("## Sampled snapshots")
    lines.append("")
    lines.append("| tick | t (s) | mode | SoC % | APU W | fuel % |")
    lines.append("| ---: | ---: | --- | ---: | ---: | ---: |")
    for s in samples:
        lines.append(
            "| {tick} | {ts:.0f} | `{mode}` | {soc:.3f} | {apu:.3f} | {fuel:.3f} |".format(
                tick=int(s["tick"]),
                ts=float(s["ts_s"]),
                mode=str(s["mode"]),
                soc=float(s["power"]["soc_pct"]),
                apu=float(s["apu"]["total_w"]),
                fuel=float(s["apu"]["fuel_pct"]),
            )
        )
    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    if trace["timeline"]:
        lines.append("| at_min | action | outcome |")
        lines.append("| ---: | --- | --- |")
        for ev in trace["timeline"]:
            args_str = ", ".join(f"{k}={v}" for k, v in (ev.get("args") or {}).items())
            action_repr = f"`{ev['action']}`"
            if args_str:
                action_repr = f"{action_repr} ({args_str})"
            lines.append(
                f"| {float(ev['at_min']):.0f} | {action_repr} | {ev['outcome']} |"
            )
    else:
        lines.append("No scenario steps recorded.")
    lines.append("")
    lines.append("## Artefacts")
    lines.append("")
    rel = f"../data/{name}.jsonl"
    lines.append(f"- raw JSONL: [`{name}.jsonl`]({rel})")
    lines.append("")
    return "\n".join(lines)


def _format_gallery_index(traces: list[tuple[str, Mapping[str, Any]]]) -> str:
    lines: list[str] = []
    lines.append("# Scenario gallery")
    lines.append("")
    lines.append(
        "Telemetry traces regenerated by "
        "`scripts/gen_showcase_telemetry.py` on every docs build."
    )
    lines.append("See [Fidelity](../fidelity.md) for the legend.")
    lines.append("")
    lines.append("| Scenario | Profile | Ticks | Final mode | Final SoC % | Final APU W |")
    lines.append("| --- | --- | ---: | --- | ---: | ---: |")
    for name, trace in traces:
        final = trace["samples"][-1] if trace["samples"] else {}
        title = trace["meta"].get("name") or name
        lines.append(
            "| [{title}]({name}.md) | `{profile}` | {ticks} | `{mode}` | {soc} | {apu} |".format(
                title=title,
                name=name,
                profile=trace["profile"],
                ticks=trace["tick_budget"],
                mode=final.get("mode", ""),
                soc=final.get("power", {}).get("soc_pct", ""),
                apu=final.get("apu", {}).get("total_w", ""),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    scenario_paths = sorted(SCENARIO_DIR.glob("*.yaml"))
    if not scenario_paths:
        print("no scenarios found; nothing to do")
        return 0

    engine_cls = _load_engine_module()
    traces: list[tuple[str, dict[str, Any]]] = []
    for path in scenario_paths:
        name = path.stem
        trace = _run_scenario(engine_cls, path)
        _write_jsonl(DATA_DIR / f"{name}.jsonl", trace)
        (GALLERY_DIR / f"{name}.md").write_text(
            _format_summary_md(name, trace), encoding="utf-8"
        )
        traces.append((name, trace))
        print(f"wrote {GALLERY_DIR / (name + '.md')}")

    (GALLERY_DIR / "README.md").write_text(
        _format_gallery_index(traces), encoding="utf-8"
    )
    print(f"wrote {GALLERY_DIR / 'README.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
