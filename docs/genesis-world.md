# Driving the twin from a Genesis world

`nous` is standalone (LIMITATIONS L17): its core never imports a physics engine,
and the world it samples for comms terrain diffraction and EO/IR line-of-sight is a
seeded procedural field by default (`TerrainModel`, ADR 0072). The world is an
injected seam, though, so an external embodied-physics simulator can drive it
without changing the default twin (ADR 0074). This page is the worked example: the
in-tree, opt-in `GenesisWorldSource` adapter (ADR 0081) backing that seam with a
real [Genesis](https://github.com/Genesis-Embodied-AI/Genesis) (`genesis-world`)
rigid-body scene.

## Install

`genesis-world` is a heavy, GPU-oriented simulator and is a manual, unlocked
dependency, not a `nous` extra, so it never enters the lock or CI and the standalone
default is unchanged. Install it yourself, torch first per the upstream notes:

```sh
pip install torch genesis-world
```

Building a scene needs a working OpenGL backend even headless, because Genesis
builds a rasterizer regardless of `show_viewer`. On a server with no display,
install OSMesa and select it:

```sh
sudo apt-get install -y libosmesa6
export PYOPENGL_PLATFORM=osmesa
```

or provide EGL (`libEGL` plus a GPU). Without a GL backend `scene.build` raises.

## Inject it into the Engine

The `Engine` takes an optional `terrain=` `WorldSource`. When supplied it overrides
the procedural default and the comms link budget and the EO/IR sightline sample it
instead, with nothing else changed. The adapter mirrors `TerrainModel`'s
equirectangular projection exactly, so it is a structural drop-in.

```python
import numpy as np
from nous.engine import Engine
from nous.subsystems.genesis_world import GenesisWorldSource

# A height field in integer units; metres = value * vertical_scale_m. Here a
# 100 m ridge across the eastern half of a 64 x 64 m patch.
height_field = np.zeros((64, 64), dtype=np.float32)
height_field[32:, :] = 100.0

world = GenesisWorldSource(
    height_field,
    horizontal_scale_m=1.0,
    vertical_scale_m=1.0,
    anchor_lat=0.0,
    anchor_lon=0.0,
)

engine = Engine(terrain=world)   # the twin now samples the Genesis world
engine.start()
for _ in range(10):
    engine.tick()

# The comms link budget and EO/IR line-of-sight ran against the Genesis terrain.
print(engine.terrain is world)            # True
print(world.elevation(0.0, 0.0))          # surface height at the anchor, metres
```

An injected world persists across `reload_profile`, so a profile hot-reload keeps
the Genesis world rather than reverting to the procedural default.

## Position and motion

The adapter also drives the platform seam. Construct it with `platform_lla` to drop
a body into the scene, then `step` advances the simulation and `position_fn` returns
the `(lat, lon, alt)` getter the comms and EO/IR subsystems accept:

```python
world = GenesisWorldSource(height_field, platform_lla=(0.0, 0.0, 50.0),
                           platform_velocity_mps=(8.0, 0.0, 0.0))
world.step(25)
lat, lon, alt = world.position_fn()()      # the body, carried east by its velocity
```

## Limitations

The adapter is validated against `genesis-world` 1.1.2. Its scene-build path needs
the dependency and a GL backend, so the end-to-end tests are opt-in
(`NOUS_GENESIS_SCENE_TESTS=1`) and skip in CI and on GL-less hosts; the projection
and interpolation are covered by tests that run everywhere. `elevation` and
`path_profile` are bilinear reads of the height field Genesis builds, captured once,
so they cost no per-query physics step.
