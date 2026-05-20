# Subsystems

Every subsystem implements the `Subsystem` Protocol
(`src/nous/subsystems/base.py`):

```python
def step(self, dt: float) -> None: ...
def truth(self) -> Mapping[str, Any]: ...
def sensor_obs(self) -> Observation: ...
```

| Subsystem | Source | Backlog |
|-----------|--------|---------|
| Power | `src/nous/subsystems/power.py` | BL-003 |
| APU | `src/nous/subsystems/apu.py` | BL-005a |
| Thermal | `src/nous/subsystems/thermal.py` | BL-005 |
| Compute | `src/nous/subsystems/compute.py` | BL-007 |
| Storage | `src/nous/subsystems/storage.py` | BL-008 |
| Sensors | `src/nous/subsystems/sensors.py` | BL-009 |
| Position | `src/nous/subsystems/position.py` | BL-010 |
| Biometrics | `src/nous/subsystems/biometrics.py` | BL-011 |
| Comms | `src/nous/subsystems/comms.py` | BL-012 |
| Inference | `src/nous/subsystems/inference.py` | BL-013 |

See [AGENTS.md](https://github.com/rmednitzer/nous/blob/main/AGENTS.md#adding-a-subsystem) for the recipe.
