"""Procedural terrain model for the moving-platform world (BL-089).

The comms link budget (:mod:`nous.subsystems.propagation`) models obstruction as a
single configured knife edge (BL-088 / ADR 0054). A real path between the device
and a peer crosses many ridges. This module supplies the missing piece: a
deterministic terrain elevation field the link budget samples along the great
circle to a peer, so a multi-edge diffraction method (Bullington) can run over a
real path profile.

The field is procedural, not a fetched digital elevation model. ``nous`` is
standalone (LIMITATIONS L17), so the world is generated from a seed rather than
loaded from an external dataset: a handful of seeded sinusoidal ridge components,
summed, give a smooth, repeatable, ridge-like surface whose horizontal scale and
relief the profile tunes. A real DEM-tile loader could implement the same
``elevation`` / ``path_profile`` interface out of tree without ``nous`` taking a
data dependency, the same seam discipline the position and RNG injections use.

Determinism: the ridge components are drawn once at construction from a
``numpy.random.Generator`` seeded from the profile (ADR 0019), so the same profile
yields the same world every run, and ``elevation`` / ``path_profile`` are pure
reads. The field is bounded in ``[base - relief, base + relief]`` by construction.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = ["TerrainModel"]

_EARTH_RADIUS_M = 6_371_000.0
_DEG_TO_M = math.pi / 180.0 * _EARTH_RADIUS_M


@dataclass(frozen=True)
class _Ridge:
    kx: float
    ky: float
    phase: float
    amp: float


class TerrainModel:
    """A deterministic procedural elevation field, sampled along a path.

    Built from a profile ``world`` block via :meth:`from_profile`, or directly for
    tests. ``elevation`` reads the height at a coordinate; ``path_profile`` samples
    the height along the great circle between two points, with ground distances, for
    the diffraction caller.
    """

    def __init__(
        self,
        *,
        anchor_lat: float = 0.0,
        anchor_lon: float = 0.0,
        base_elevation_m: float = 0.0,
        relief_m: float = 0.0,
        feature_m: float = 5000.0,
        components: int = 8,
        seed: int = 0,
    ) -> None:
        self.anchor_lat = anchor_lat
        self.anchor_lon = anchor_lon
        self.base_elevation_m = base_elevation_m
        self.relief_m = max(0.0, relief_m)
        self._cos_anchor = math.cos(math.radians(anchor_lat))
        n = max(1, components)
        rng = np.random.default_rng(seed)
        amp = self.relief_m / float(n)
        wavelength_lo = max(1.0, feature_m * 0.5)
        wavelength_hi = max(wavelength_lo, feature_m * 2.0)
        ridges: list[_Ridge] = []
        for _ in range(n):
            wavelength = float(rng.uniform(wavelength_lo, wavelength_hi))
            angle = float(rng.uniform(0.0, 2.0 * math.pi))
            k = 2.0 * math.pi / wavelength
            ridges.append(
                _Ridge(
                    kx=k * math.cos(angle),
                    ky=k * math.sin(angle),
                    phase=float(rng.uniform(0.0, 2.0 * math.pi)),
                    amp=amp,
                )
            )
        self._ridges: tuple[_Ridge, ...] = tuple(ridges)

    @classmethod
    def from_profile(cls, profile: Mapping[str, Any]) -> TerrainModel | None:
        """Build a model from a profile ``world`` block, or ``None`` when absent.

        Returns ``None`` when the block is missing, malformed, or explicitly
        disabled (``enabled: false``), so a link falls back to the single
        knife-edge model and a profile with no ``world`` section is unchanged.
        """
        block = profile.get("world")
        if not isinstance(block, Mapping):
            return None
        if not bool(block.get("enabled", True)):
            return None

        def _f(key: str, default: float) -> float:
            try:
                return float(block.get(key, default))
            except (TypeError, ValueError):
                return default

        def _i(key: str, default: int) -> int:
            try:
                return int(block.get(key, default))
            except (TypeError, ValueError):
                return default

        return cls(
            anchor_lat=_f("anchor_lat", 0.0),
            anchor_lon=_f("anchor_lon", 0.0),
            base_elevation_m=_f("base_elevation_m", 0.0),
            relief_m=_f("relief_m", 0.0),
            feature_m=_f("feature_m", 5000.0),
            components=_i("components", 8),
            seed=_i("seed", 0),
        )

    def _local_xy(self, lat: float, lon: float) -> tuple[float, float]:
        dx = (lon - self.anchor_lon) * _DEG_TO_M * self._cos_anchor
        dy = (lat - self.anchor_lat) * _DEG_TO_M
        return dx, dy

    def elevation(self, lat: float, lon: float) -> float:
        """Terrain elevation in metres at ``(lat, lon)``."""
        dx, dy = self._local_xy(lat, lon)
        total = self.base_elevation_m
        for r in self._ridges:
            total += r.amp * math.sin(r.kx * dx + r.ky * dy + r.phase)
        return total

    def path_profile(
        self, lat1: float, lon1: float, lat2: float, lon2: float, n: int
    ) -> list[tuple[float, float]]:
        """Sample ``n`` terrain elevations along the path, with ground distances.

        Returns ``[(distance_from_p1_m, elevation_m), ...]`` including both
        endpoints, linearly interpolating ``(lat, lon)`` (exact enough over the
        tens-of-kilometres ranges the twin models). A diffraction caller supplies
        the device and peer antenna heights separately and uses only the interior
        points as candidate edges.
        """
        count = max(2, n)
        total = _ground_distance_m(lat1, lon1, lat2, lon2)
        out: list[tuple[float, float]] = []
        for i in range(count):
            frac = i / (count - 1)
            lat = lat1 + (lat2 - lat1) * frac
            lon = lon1 + (lon2 - lon1) * frac
            out.append((total * frac, self.elevation(lat, lon)))
        return out


def _ground_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    return 2.0 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))
