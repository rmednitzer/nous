"""Unit tests for the BL-089 procedural terrain model."""

from __future__ import annotations

import numpy as np

from nous.subsystems.terrain import TerrainModel


def test_flat_terrain_at_zero_relief() -> None:
    t = TerrainModel(base_elevation_m=500.0, relief_m=0.0, seed=1)
    assert t.elevation(47.0, 13.0) == 500.0
    assert t.elevation(47.5, 13.5) == 500.0


def test_elevation_is_deterministic_under_seed() -> None:
    a = TerrainModel(base_elevation_m=400.0, relief_m=300.0, feature_m=700.0, seed=7)
    b = TerrainModel(base_elevation_m=400.0, relief_m=300.0, feature_m=700.0, seed=7)
    assert a.elevation(47.01, 13.02) == b.elevation(47.01, 13.02)


def test_different_seeds_differ() -> None:
    a = TerrainModel(base_elevation_m=400.0, relief_m=300.0, seed=1)
    b = TerrainModel(base_elevation_m=400.0, relief_m=300.0, seed=2)
    assert a.elevation(47.123, 13.456) != b.elevation(47.123, 13.456)


def test_relief_is_bounded() -> None:
    t = TerrainModel(
        base_elevation_m=500.0, relief_m=200.0, feature_m=500.0, components=8, seed=3
    )
    rng = np.random.default_rng(0)
    for _ in range(2000):
        lat = 47.0 + float(rng.uniform(-0.5, 0.5))
        lon = 13.0 + float(rng.uniform(-0.5, 0.5))
        e = t.elevation(lat, lon)
        assert 300.0 - 1e-6 <= e <= 700.0 + 1e-6


def test_path_profile_endpoints_and_distance() -> None:
    t = TerrainModel(base_elevation_m=450.0, relief_m=300.0, feature_m=700.0, seed=7)
    prof = t.path_profile(47.0, 13.0, 47.0, 12.98, 24)
    assert len(prof) == 24
    assert prof[0][0] == 0.0
    # ~1.5 km for 0.02 deg of longitude at 47 N.
    assert 1400.0 < prof[-1][0] < 1700.0
    dists = [d for d, _ in prof]
    assert dists == sorted(dists)


def test_from_profile_none_without_world() -> None:
    assert TerrainModel.from_profile({"name": "x"}) is None
    assert TerrainModel.from_profile({"world": {"enabled": False}}) is None
    assert TerrainModel.from_profile({"world": "not-a-mapping"}) is None


def test_from_profile_reads_fields() -> None:
    t = TerrainModel.from_profile(
        {"world": {"base_elevation_m": 400, "relief_m": 300, "seed": 7}}
    )
    assert t is not None
    assert t.base_elevation_m == 400.0
    assert t.relief_m == 300.0
