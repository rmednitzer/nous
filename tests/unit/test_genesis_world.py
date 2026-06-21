"""Tests for the optional Genesis-backed WorldSource adapter (ADR 0081).

The projection, interpolation, and path sampling are pure math and run
everywhere. The Genesis scene-build path needs both the optional genesis-world
dependency and a working OpenGL backend (Genesis builds a rasterizer even
headless), so it is gated on an explicit opt-in env var and skips in CI and on
GL-less hosts. To run it: install genesis-world plus a GL backend (for example
`libosmesa6` with `PYOPENGL_PLATFORM=osmesa`, or EGL with a GPU) and set
`NOUS_GENESIS_SCENE_TESTS=1`.
"""

from __future__ import annotations

import importlib.util
import os
import traceback
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from nous.engine import Engine
from nous.self_model.assess import assess
from nous.subsystems.genesis_world import (
    GenesisWorldSource,
    _bilinear,
    _elevation_from_field,
    _project_local_xy,
    _sample_path,
)
from nous.subsystems.terrain import _DEG_TO_M, TerrainModel, WorldSource

_GENESIS = importlib.util.find_spec("genesis") is not None
_RUN_SCENE = _GENESIS and os.environ.get("NOUS_GENESIS_SCENE_TESTS") == "1"
_METRE_DEG = 1.0 / _DEG_TO_M  # one metre expressed in degrees at the equator


# --- pure-math core: runs everywhere, no Genesis needed ---


def test_projection_matches_terrain_convention() -> None:
    """The adapter must project (lat, lon) identically to TerrainModel, so it is
    a drop-in for the comms/EO-IR seams rather than a subtly different frame."""
    terrain = TerrainModel(anchor_lat=47.0, anchor_lon=8.0, relief_m=0.0)
    for lat, lon in [(47.0, 8.0), (47.1, 8.05), (46.9, 7.9)]:
        adapter_xy = _project_local_xy(
            lat, lon, terrain.anchor_lat, terrain.anchor_lon, terrain._cos_anchor
        )
        assert adapter_xy == pytest.approx(terrain._local_xy(lat, lon))


def test_projection_directions() -> None:
    """East of the anchor is +dx (east metres), north is +dy (north metres)."""
    east = _project_local_xy(0.0, 0.01, 0.0, 0.0, 1.0)
    north = _project_local_xy(0.01, 0.0, 0.0, 0.0, 1.0)
    assert east[0] > 0.0 and east[1] == pytest.approx(0.0)
    assert north[1] > 0.0 and north[0] == pytest.approx(0.0)


def test_bilinear_interpolates_corners_and_midpoints() -> None:
    field = np.array([[0.0, 10.0], [20.0, 30.0]])
    assert _bilinear(field, 0.0, 0.0) == pytest.approx(0.0)
    assert _bilinear(field, 0.0, 1.0) == pytest.approx(10.0)
    assert _bilinear(field, 1.0, 0.0) == pytest.approx(20.0)
    assert _bilinear(field, 1.0, 1.0) == pytest.approx(30.0)
    assert _bilinear(field, 0.5, 0.5) == pytest.approx(15.0)
    assert _bilinear(field, -5.0, 9.0) == pytest.approx(10.0)  # clamps to edge


def test_elevation_from_field_2d_ramp() -> None:
    """Pin the full project -> index -> bilinear -> scale pipeline with a field
    where height encodes (row, col): east (dx) selects the row, north (dy) the
    column. Uses the exact metre-per-degree so indices land on integers."""
    field = np.array([[r * 10.0 + c for c in range(6)] for r in range(6)])

    def elev(lat: float, lon: float) -> float:
        return _elevation_from_field(
            field,
            horizontal_scale_m=1.0,
            vertical_scale_m=1.0,
            origin_xy_m=(0.0, 0.0),
            base_elevation_m=0.0,
            anchor_lat=0.0,
            anchor_lon=0.0,
            cos_anchor=1.0,
            lat=lat,
            lon=lon,
        )

    assert elev(0.0, 0.0) == pytest.approx(0.0)  # row 0, col 0
    assert elev(0.0, 3 * _METRE_DEG) == pytest.approx(30.0)  # dx -> row 3
    assert elev(3 * _METRE_DEG, 0.0) == pytest.approx(3.0)  # dy -> col 3
    assert elev(2 * _METRE_DEG, 4 * _METRE_DEG) == pytest.approx(42.0)  # row 4, col 2


def test_elevation_scale_and_base_offset() -> None:
    field = np.array([[2.0, 2.0], [2.0, 2.0]])
    elev = _elevation_from_field(
        field,
        horizontal_scale_m=1.0,
        vertical_scale_m=5.0,
        origin_xy_m=(0.0, 0.0),
        base_elevation_m=100.0,
        anchor_lat=0.0,
        anchor_lon=0.0,
        cos_anchor=1.0,
        lat=0.0,
        lon=0.0,
    )
    assert elev == pytest.approx(2.0 * 5.0 + 100.0)


def test_sample_path_structure_and_distances() -> None:
    profile = _sample_path(lambda lat, lon: 42.0, 0.0, 0.0, 0.0, 0.1, 5)
    assert len(profile) == 5
    assert profile[0][0] == pytest.approx(0.0)
    assert all(elev == pytest.approx(42.0) for _, elev in profile)
    distances = [d for d, _ in profile]
    assert distances == sorted(distances)
    assert distances[-1] > distances[0]


def test_sample_path_reflects_varying_elevation() -> None:
    """A north-running path over an elevation that grows with latitude returns a
    monotonically rising profile."""
    profile = _sample_path(lambda lat, lon: lat * 1000.0, 0.0, 0.0, 0.05, 0.0, 6)
    elevations = [e for _, e in profile]
    assert elevations == sorted(elevations)
    assert elevations[-1] > elevations[0]


@pytest.mark.skipif(_GENESIS, reason="genesis-world is installed")
def test_constructor_without_extra_raises_helpful_error() -> None:
    """Without the optional dependency the adapter fails loudly with install
    guidance, and the module itself imports with no genesis."""
    with pytest.raises(ModuleNotFoundError, match="genesis-world"):
        GenesisWorldSource(np.zeros((4, 4)))


def test_constructor_rejects_bad_height_field() -> None:
    with pytest.raises(ValueError, match="2D"):
        GenesisWorldSource(np.zeros((4,)))  # 1D
    with pytest.raises(ValueError, match="2D"):
        GenesisWorldSource(np.zeros((0, 0)))  # empty


# --- Genesis scene path: opt-in, needs genesis-world + a GL backend ---

_GL_MARKERS = ("egl", "osmesa", "opengl", "glx", "rasterizer", "visualizer", "no display")


def _build_or_skip(make: Callable[[], GenesisWorldSource]) -> GenesisWorldSource:
    """Build a scene, or skip if it fails for lack of a GL backend.

    Genesis builds a rasterizer at `scene.build()` even headless, so on a host
    with the dependency but no EGL/OSMesa the build raises. The pre-build logic
    is covered by the pure-math tests, so a GL failure here is environmental and
    skips; any non-GL error still propagates so a real regression is not masked.
    """
    try:
        return make()
    except Exception as exc:
        if any(marker in traceback.format_exc().lower() for marker in _GL_MARKERS):
            pytest.skip(f"Genesis scene build needs a GL backend: {exc!r}")
        raise


@pytest.mark.skipif(
    not _RUN_SCENE,
    reason="needs genesis-world + a GL backend + NOUS_GENESIS_SCENE_TESTS=1",
)
def test_genesis_scene_tracks_terrain_and_platform_motion() -> None:
    """End-to-end against a live Genesis scene: a step terrain is read back
    through the WorldSource contract, and a platform given an eastward velocity
    actually moves east (exercising the set_dofs_velocity path)."""
    field = np.zeros((32, 32), dtype=np.float32)
    field[16:, :] = 100.0  # a step in the row (east) direction, 100 m high

    src = _build_or_skip(
        lambda: GenesisWorldSource(
            field,
            horizontal_scale_m=1.0,
            vertical_scale_m=1.0,
            platform_lla=(0.0, 0.0, 50.0),
            platform_velocity_mps=(8.0, 0.0, 0.0),
        )
    )
    assert isinstance(src, WorldSource)

    low = src.elevation(0.0, 4 * _METRE_DEG)  # row 4: low side
    high = src.elevation(0.0, 28 * _METRE_DEG)  # row 28: high side
    assert low < 10.0
    assert high > 90.0
    assert high - low > 50.0

    profile = src.path_profile(0.0, 4 * _METRE_DEG, 0.0, 28 * _METRE_DEG, 8)
    assert len(profile) == 8
    assert profile[0][0] == pytest.approx(0.0)
    assert profile[-1][1] > profile[0][1] + 50.0

    _, lon0, _ = src.platform_position()
    src.step(25)
    lat1, lon1, alt1 = src.platform_position()
    assert all(np.isfinite(v) for v in (lat1, lon1, alt1))
    assert lon1 > lon0  # eastward velocity carried the body east


@pytest.mark.skipif(
    not _RUN_SCENE,
    reason="needs genesis-world + a GL backend + NOUS_GENESIS_SCENE_TESTS=1",
)
def test_genesis_scene_no_platform_position_raises() -> None:
    src = _build_or_skip(lambda: GenesisWorldSource(np.zeros((8, 8), dtype=np.float32)))
    with pytest.raises(RuntimeError, match="no platform"):
        src.platform_position()


@pytest.mark.skipif(
    not _RUN_SCENE,
    reason="needs genesis-world + a GL backend + NOUS_GENESIS_SCENE_TESTS=1",
)
def test_engine_runs_against_genesis_world(tmp_nous_home: Path) -> None:
    """The worked example (docs/genesis-world.md): inject a GenesisWorldSource into
    the Engine `terrain=` seam and tick the twin against a live Genesis scene."""
    field = np.zeros((32, 32), dtype=np.float32)
    field[16:, :] = 100.0
    world = _build_or_skip(
        lambda: GenesisWorldSource(field, horizontal_scale_m=1.0, vertical_scale_m=1.0)
    )
    eng = Engine(terrain=world)
    assert eng.terrain is world
    eng.start()
    for _ in range(5):
        eng.tick()
    a = assess("status", engine=eng)
    assert a.endurance is not None
