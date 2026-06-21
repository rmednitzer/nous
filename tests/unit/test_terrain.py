"""Unit tests for the BL-089 procedural terrain model."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from nous.engine import Engine
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


def test_terrain_model_satisfies_world_source_protocol() -> None:
    from nous.subsystems.terrain import WorldSource

    t = TerrainModel(relief_m=100.0, seed=1)
    assert isinstance(t, WorldSource)


def test_custom_world_source_drives_comms_terrain() -> None:
    # ADR 0074: any WorldSource, not just the in-tree TerrainModel, plugs into the
    # comms terrain seam, the standalone-to-external boundary.
    from nous.subsystems.comms import CommsSubsystem

    class RidgeWorld:
        def elevation(self, lat: float, lon: float) -> float:
            return 800.0

        def path_profile(
            self, lat1: float, lon1: float, lat2: float, lon2: float, n: int
        ) -> list[tuple[float, float]]:
            return [(0.0, 500.0), (2000.0, 800.0), (4000.0, 500.0)]

    def _profile() -> dict[str, object]:
        return {
            "comms": {
                "links": [
                    {
                        "id": "relay",
                        "bandwidth_bps": 2_000_000,
                        "max_age_s": 600.0,
                        "propagation": {
                            "peer": {"lat": 47.0, "lon": 12.96, "alt_m": 500.0},
                            "use_terrain": True,
                            "tx_power_dbm": 20.0,
                        },
                    }
                ]
            }
        }

    with_world = CommsSubsystem(
        _profile(), position_fn=lambda: (47.0, 13.0, 500.0), terrain=RidgeWorld()
    )
    without = CommsSubsystem(_profile(), position_fn=lambda: (47.0, 13.0, 500.0))
    with_world.step(1.0)
    without.step(1.0)
    blocked = with_world.link("relay")
    clear = without.link("relay")
    assert blocked is not None and clear is not None
    assert blocked.path_loss_db is not None and clear.path_loss_db is not None
    # The injected ridge added multi-edge diffraction loss over the path.
    assert blocked.path_loss_db > clear.path_loss_db


class _FakeWorld:
    """A minimal WorldSource (no genesis), to test the Engine injection seam.

    Deliberately falsy (`__bool__` returns False) so the injection must be
    selected by `is not None`, not truthiness: with a `terrain or default` check
    this world would be silently dropped and the assertions below would fail.
    """

    def __bool__(self) -> bool:
        return False

    def elevation(self, lat: float, lon: float) -> float:
        return 1234.0

    def path_profile(
        self, lat1: float, lon1: float, lat2: float, lon2: float, n: int
    ) -> list[tuple[float, float]]:
        return [(0.0, 1234.0), (1.0, 1234.0)]


def test_engine_uses_injected_world_source(tmp_nous_home: Path) -> None:
    """ADR 0074/0081: an Engine `terrain=` WorldSource overrides the procedural
    default and persists across a profile reload, so an external world (such as a
    GenesisWorldSource) drives the twin without `nous` importing it. Injection is
    opt-in: a default Engine does not pick it up."""
    fake = _FakeWorld()
    eng = Engine(terrain=fake)
    assert eng.terrain is fake
    eng.reload_profile()
    assert eng.terrain is fake

    default = Engine()
    assert default.terrain is not fake
