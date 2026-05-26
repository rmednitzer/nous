"""Scenario step injectors (BL-014).

A scenario step is a tuple ``(at_min, action, args)``. The runner
calls :func:`apply_injection` with the engine handle, the action
name, and the args; this module translates the action into the
matching subsystem mutation. Each injector returns a JSON-safe
mapping describing what it changed so the runner can record it on
the audit trail.

Supported actions:

* ``state_transition`` -- drive the FSM through a trigger
  (``trigger``, optional ``context``).
* ``inject_biometrics`` -- shift HR / core temp / hydration /
  cognitive load by ``*_delta`` or set absolute values with the
  unprefixed key (e.g. ``heart_rate_bpm``).
* ``inject_thermal`` -- shift ambient temperature
  (``ambient_delta_c``) or set absolute load (``load_w``).
* ``inject_apu`` -- override per-source APU outputs (``solar_w``,
  ``fuelcell_w``, ``vehicle_w``, ``usbc_w``).
* ``inject_comms_loss`` -- raise the loss percentage on a specific
  link (``link_id``, ``loss_pct``); a value of 100 cuts the link.
* ``inject_sensor_drift`` -- nudge a sensor source. Today supports
  ``source: position`` with ``north_mps`` and ``east_mps`` (IMU drift
  velocities applied when GNSS fix is lost). Legacy ``lat_bias_m`` /
  ``lon_bias_m`` aliases are accepted but interpreted as m/s drift,
  not metres of position bias, so scenario authors should prefer the
  ``*_mps`` names for clarity.
* ``inject_position`` -- teleport ground truth (``lat``, ``lon``,
  optional ``alt_m``).
* ``inject_velocity`` -- set the dead-reckoning velocity vector
  (``speed_mps``, ``heading_deg``, optional ``vertical_mps``).
* ``inject_compute`` -- set the requested load fraction
  (``load_pct``) or token rate (``tok_per_s``).
* ``inference_request`` -- run one local inference call with
  ``prompt`` and optional ``max_tokens``.

Unknown actions are reported as ``{"action": ..., "applied": false,
"error": "unknown action"}``. The runner does not raise; it records
the skip so the audit trail explains the outage.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..engine import Engine

__all__ = ["INJECTORS", "InjectionResult", "apply_injection"]


InjectionResult = dict[str, Any]


def apply_injection(
    engine: Engine,
    action: str,
    args: Mapping[str, Any] | None = None,
) -> InjectionResult:
    """Dispatch ``action`` against ``engine`` with ``args``.

    Returns a JSON-safe mapping ``{"action", "args", "applied",
    "result?", "error?"}`` so the runner can mirror the step into
    the audit trail.

    An injector that ran without raising but signalled a soft refusal
    via ``{"ok": False, "reason": ...}`` (the shape ``_state_transition``
    uses for guard denials) is recorded as ``applied=False`` with the
    reason copied to ``error``. This keeps the report's
    ``steps_fired`` / ``steps_skipped`` counters honest: a denied FSM
    transition produces no state change and must not look fired in the
    summary.
    """
    args = dict(args or {})
    fn = INJECTORS.get(action)
    if fn is None:
        return {"action": action, "args": args, "applied": False, "error": "unknown action"}
    try:
        result = fn(engine, args)
    except Exception as exc:  # noqa: BLE001
        return {
            "action": action,
            "args": args,
            "applied": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    if isinstance(result, Mapping) and result.get("ok") is False:
        return {
            "action": action,
            "args": args,
            "applied": False,
            "result": dict(result),
            "error": str(result.get("reason", "soft refusal")),
        }
    return {"action": action, "args": args, "applied": True, "result": result}


def _state_transition(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    trigger = str(args.get("trigger", ""))
    if not trigger:
        raise ValueError("state_transition requires 'trigger'")
    context = args.get("context")
    ctx = dict(context) if isinstance(context, Mapping) else None
    ok, mode, reason = engine.request_transition(trigger, context=ctx)
    return {"ok": ok, "mode": mode.value, "reason": reason}


def _inject_biometrics(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    sub = engine.biometrics
    changes: dict[str, float] = {}
    for key, fn in (
        ("heart_rate_bpm", sub.set_heart_rate_bpm),
        ("core_temp_c", sub.set_core_temp_c),
        ("hydration_pct", sub.set_hydration_pct),
        ("cognitive_load", sub.set_cognitive_load),
    ):
        if key in args:
            value = float(args[key])
            fn(value)
            changes[key] = float(getattr(sub, key))
    for delta_key, attr_name, setter in (
        ("heart_rate_bpm_delta", "heart_rate_bpm", sub.set_heart_rate_bpm),
        ("core_temp_c_delta", "core_temp_c", sub.set_core_temp_c),
        ("hydration_pct_delta", "hydration_pct", sub.set_hydration_pct),
        ("cognitive_load_delta", "cognitive_load", sub.set_cognitive_load),
    ):
        if delta_key in args:
            current = float(getattr(sub, attr_name))
            new_value = current + float(args[delta_key])
            setter(new_value)
            changes[attr_name] = float(getattr(sub, attr_name))
    return changes


def _inject_thermal(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    sub = engine.thermal
    sensors = engine.sensors
    changes: dict[str, float] = {}
    if "ambient_delta_c" in args:
        new_temp = sensors.temp_c + float(args["ambient_delta_c"])
        sensors.set_temp_c(new_temp)
        sub.set_ambient_c(new_temp)
        changes["sensors.temp_c"] = float(sensors.temp_c)
        changes["thermal.ambient_c"] = float(sub.ambient_c)
    if "ambient_c" in args:
        sensors.set_temp_c(float(args["ambient_c"]))
        sub.set_ambient_c(float(args["ambient_c"]))
        changes["sensors.temp_c"] = float(sensors.temp_c)
        changes["thermal.ambient_c"] = float(sub.ambient_c)
    if "load_w" in args:
        sub.set_load_w(float(args["load_w"]))
        changes["thermal.load_w"] = float(sub.load_w)
    return changes


def _inject_apu(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    apu = engine.apu
    changes: dict[str, Any] = {}
    if "solar_w" in args:
        apu.set_solar_w(float(args["solar_w"]))
        changes["solar_w"] = float(args["solar_w"])
    if "fuelcell_w" in args:
        apu.set_fuelcell_w(float(args["fuelcell_w"]))
        changes["fuelcell_w"] = float(args["fuelcell_w"])
    if "vehicle_w" in args:
        watts = float(args["vehicle_w"])
        apu.set_vehicle(connected=watts > 0.0, offered_w=watts)
        changes["vehicle_w"] = watts
    if "usbc_w" in args:
        watts = float(args["usbc_w"])
        apu.set_usb_c_pd(connected=watts > 0.0, profile_w=watts if watts > 0.0 else None)
        changes["usbc_w"] = watts
    return changes


def _inject_comms_loss(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    link_id = str(args.get("link_id", ""))
    if not link_id:
        raise ValueError("inject_comms_loss requires 'link_id'")
    if "loss_pct" not in args:
        raise ValueError("inject_comms_loss requires 'loss_pct'")
    loss_pct = float(args["loss_pct"])
    connected: bool | None = None
    if loss_pct >= 100.0:
        connected = False
    elif loss_pct <= 0.0 and engine.comms.link(link_id) is not None:
        connected = True
    engine.comms.set_link_state(
        link_id, loss_pct=loss_pct, connected=connected
    )
    link = engine.comms.link(link_id)
    return {
        "link_id": link_id,
        "loss_pct": loss_pct,
        "connected": link.is_live() if link is not None else False,
    }


def _inject_sensor_drift(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    source = str(args.get("source", "")).lower()
    if source != "position":
        raise ValueError(f"unsupported sensor source {source!r}")
    pos = engine.position
    north_mps = float(args.get("north_mps", args.get("lat_bias_m", 0.0)))
    east_mps = float(args.get("east_mps", args.get("lon_bias_m", 0.0)))
    pos.set_imu_drift(north_mps=north_mps, east_mps=east_mps)
    return {"source": source, "north_mps": north_mps, "east_mps": east_mps}


def _inject_position(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    lat = float(args["lat"])
    lon = float(args["lon"])
    alt_m = args.get("alt_m")
    engine.position.set_position(
        lat, lon, alt_m=None if alt_m is None else float(alt_m)
    )
    return {"lat": lat, "lon": lon, "alt_m": float(alt_m) if alt_m is not None else None}


def _inject_velocity(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    speed = float(args.get("speed_mps", 0.0))
    heading = float(args.get("heading_deg", 0.0))
    vertical = float(args.get("vertical_mps", 0.0))
    engine.position.set_velocity(speed, heading, vertical_mps=vertical)
    return {"speed_mps": speed, "heading_deg": heading, "vertical_mps": vertical}


def _inject_compute(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    changes: dict[str, float] = {}
    if "load_pct" in args:
        engine.compute.set_load_pct(float(args["load_pct"]))
        changes["load_pct"] = float(engine.compute.load_pct)
    if "tok_per_s" in args:
        engine.compute.set_inference_rate(float(args["tok_per_s"]))
        changes["tok_per_s"] = float(args["tok_per_s"])
    return changes


def _inference_request(engine: Engine, args: Mapping[str, Any]) -> InjectionResult:
    prompt = str(args.get("prompt", ""))
    max_tokens = int(args.get("max_tokens", 64))
    result = engine.inference.request_local(prompt, max_tokens=max_tokens)
    return result.to_dict()


INJECTORS: dict[str, Any] = {
    "state_transition": _state_transition,
    "inject_biometrics": _inject_biometrics,
    "inject_thermal": _inject_thermal,
    "inject_apu": _inject_apu,
    "inject_comms_loss": _inject_comms_loss,
    "inject_sensor_drift": _inject_sensor_drift,
    "inject_position": _inject_position,
    "inject_velocity": _inject_velocity,
    "inject_compute": _inject_compute,
    "inference_request": _inference_request,
}
