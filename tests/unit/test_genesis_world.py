"""Tests for the optional Genesis-backed WorldSource adapter (ADR 0081).

The projection and interpolation are pure math and run everywhere; the
scene-build path needs the optional ``genesis`` extra and is gated on it, so the
suite stays green whether or not the extra is installed (it is not, in CI).
"""

from __future__ import annotations

import importlib.util

import numpy as np
import pytest

from nous.subsystems.genesis_world import (
    GenesisWorldSource,
    _bilinear,
    _elevation_from_field,
    _project_local_xy,
    _sample_path,
)
from nous.subsystems.terrain import TerrainModel, WorldSource

_GENESIS = importlib.util.find_spec("genesis") is not None


def test_projection_matches_terrain_convention() -> None:
    """The adapter must project (lat, lon) identically to TerrainModel, so it is
    a drop-in for the comms/EO-IR seams rather than a subtly different frame."""
    terrain = TerrainModel(anchor_lat=47.0, anchor_lon=8.0, relief_m=0.0)
    for lat, lon in [(47.0, 8.0), (47.1, 8.05), (46.9, 7.9)]:
        adapter_xy = _project_local_xy(
            lat, lon, terrain.anchor_lat, terrain.anchor_lon, terrain._cos_anchor
        )
        assert adapter_xy == pytest.approx(terrain._local_xy(lat, lon))


def test_bilinear_interpolates_corners_and_midpoints() -> None:
    field = np.array([[0.0, 10.0], [20.0, 30.0]])
    assert _bilinear(field, 0.0, 0.0) == pytest.approx(0.0)
    assert _bilinear(field, 0.0, 1.0) == pytest.approx(10.0)
    assert _bilinear(field, 1.0, 0.0) == pytest.approx(20.0)
    assert _bilinear(field, 1.0, 1.0) == pytest.approx(30.0)
    assert _bilinear(field, 0.5, 0.5) == pytest.approx(15.0)
    # Out-of-range indices clamp to the edge rather than raising.
    assert _bilinear(field, -5.0, 9.0) == pytest.approx(10.0)


def test_elevation_from_field_reads_a_ramp() -> None:
    """A north-south ramp: height grows with the row index (scene x = east dx)."""
    field = np.array([[float(r)] * 3 for r in range(5)])  # height == row index
    elev = _elevation_from_field(
        field,
        horizontal_scale_m=1.0,
        vertical_scale_m=2.0,
        origin_xy_m=(0.0, 0.0),
        base_elevation_m=10.0,
        anchor_lat=0.0,
        anchor_lon=0.0,
        cos_anchor=1.0,
        lat=0.0,
        lon=0.0,
    )
    # At the anchor, dx == 0 -> row 0 -> field 0 -> 0 * 2 + 10.
    assert elev == pytest.approx(10.0)


def test_sample_path_structure_and_distances() -> None:
    profile = _sample_path(lambda lat, lon: 42.0, 0.0, 0.0, 0.0, 0.1, 5)
    assert len(profile) == 5
    assert profile[0][0] == pytest.approx(0.0)
    assert all(elev == pytest.approx(42.0) for _, elev in profile)
    distances = [d for d, _ in profile]
    assert distances == sorted(distances)
    assert distances[-1] > distances[0]


@pytest.mark.skipif(_GENESIS, reason="genesis extra is installed")
def test_constructor_without_extra_raises_helpful_error() -> None:
    """Without the optional extra the adapter fails loudly with install guidance,
    and the core stays standalone (the module itself imports with no genesis)."""
    with pytest.raises(ModuleNotFoundError, match="genesis-world"):
        GenesisWorldSource(np.zeros((4, 4)))


@pytest.mark.skipif(not _GENESIS, reason="needs the optional genesis extra")
def test_genesis_world_source_is_a_worldsource() -> None:
    field = np.zeros((16, 16), dtype=np.float32)
    field[8:, :] = 100.0
    src = GenesisWorldSource(
        field,
        horizontal_scale_m=1.0,
        vertical_scale_m=1.0,
        platform_lla=(0.0, 0.0, 50.0),
    )
    assert isinstance(src, WorldSource)
    assert isinstance(src.elevation(0.0, 0.0), float)

    profile = src.path_profile(0.0, 0.0, 0.001, 0.0, 8)
    assert len(profile) == 8
    assert profile[0][0] == pytest.approx(0.0)
    assert [d for d, _ in profile] == sorted(d for d, _ in profile)

    src.step(5)
    lat, lon, alt = src.platform_position()
    assert isinstance(lat, float) and isinstance(lon, float) and isinstance(alt, float)
