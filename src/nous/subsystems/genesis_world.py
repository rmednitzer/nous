"""Genesis-backed ``WorldSource`` adapter (ADR 0074 seam, opt-in in-tree).

``nous`` is standalone (LIMITATIONS L17): the core import graph never imports a
physics engine. This module is the opt-in exception ADR 0074 anticipated, an
adapter that satisfies the :class:`~nous.subsystems.terrain.WorldSource` Protocol
(and the comms / EO-IR ``position_fn`` seam) from a headless Genesis
(``genesis-world``) rigid-body scene, so the comms link budget and the EO/IR
line-of-sight can run against an engine-simulated world instead of the procedural
``TerrainModel``. Nothing in the core imports this module and ``genesis`` is
imported lazily inside the constructor, so the twin stays import-clean and
standalone when ``genesis-world`` is not installed (ADR 0081).

``genesis-world`` is a deliberately unlocked, manual dependency (it is heavy and
needs a platform-appropriate ``torch`` installed first), so it is not a
``nous`` extra and never enters the lock or CI. Install it yourself to use the
adapter::

    pip install torch genesis-world      # torch first, per the upstream notes

Building a scene needs a working OpenGL backend even headless, because Genesis
builds a rasterizer regardless of ``show_viewer``: on a server with no display,
install OSMesa (``libosmesa6``) and set ``PYOPENGL_PLATFORM=osmesa``, or provide
EGL (``libEGL`` plus a GPU). Without a GL backend ``scene.build`` raises.

Coordinate convention mirrors ``TerrainModel`` so an instance is a drop-in
wherever a ``TerrainModel`` is injected: a horizontal ``(lat, lon)`` maps through
the same equirectangular projection from an anchor (``_DEG_TO_M``,
``cos(anchor_lat)``) to local metres, then to scene ``(x, y)``, and the surface
height is a bilinear read of the height field Genesis built (its
``geoms[0].metadata["height_field"]``, the field the rigid-body physics uses), so
the elevation the link budget sees is the elevation a body would rest on. The
field is captured once at build, so ``elevation`` / ``path_profile`` are pure
reads with no per-query physics step.

The position / motion seam is optional: pass ``platform_lla`` to drop a body into
the scene, then :meth:`step` advances the simulation and :meth:`position_fn`
returns the ``Callable[[], tuple[float, float, float]]`` the comms and EO/IR
subsystems accept, reading the body's pose back as ``(lat, lon, alt)``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import numpy as np

from .terrain import _DEG_TO_M, _ground_distance_m

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["GenesisWorldSource"]

PositionFn = Callable[[], tuple[float, float, float]]

_gs_initialized = False


def _import_genesis() -> Any:
    try:
        import genesis as gs
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised without the extra
        raise ModuleNotFoundError(
            "GenesisWorldSource needs genesis-world (a manual, unlocked "
            "dependency): pip install torch genesis-world. "
            "nous stays standalone without it (LIMITATIONS L17)."
        ) from exc
    return gs


def _ensure_init(gs: Any, backend: str) -> None:
    """Initialise Genesis once per process (it is a global, single-init engine)."""
    global _gs_initialized
    if _gs_initialized:
        return
    gs.init(backend=gs.cpu if backend == "cpu" else gs.gpu)
    _gs_initialized = True


def _project_local_xy(
    lat: float, lon: float, anchor_lat: float, anchor_lon: float, cos_anchor: float
) -> tuple[float, float]:
    """Equirectangular ``(lat, lon) -> (east_m, north_m)``, mirroring TerrainModel."""
    dx = (lon - anchor_lon) * _DEG_TO_M * cos_anchor
    dy = (lat - anchor_lat) * _DEG_TO_M
    return dx, dy


def _bilinear(field: np.ndarray, row: float, col: float) -> float:
    """Bilinear sample of a 2D field at fractional ``(row, col)``, clamped to bounds."""
    rows, cols = field.shape
    r0 = int(min(max(math.floor(row), 0), rows - 1))
    c0 = int(min(max(math.floor(col), 0), cols - 1))
    r1 = min(r0 + 1, rows - 1)
    c1 = min(c0 + 1, cols - 1)
    dr = min(max(row - r0, 0.0), 1.0)
    dc = min(max(col - c0, 0.0), 1.0)
    top = field[r0, c0] * (1.0 - dc) + field[r0, c1] * dc
    bot = field[r1, c0] * (1.0 - dc) + field[r1, c1] * dc
    return float(top * (1.0 - dr) + bot * dr)


def _elevation_from_field(
    field: np.ndarray,
    *,
    horizontal_scale_m: float,
    vertical_scale_m: float,
    origin_xy_m: tuple[float, float],
    base_elevation_m: float,
    anchor_lat: float,
    anchor_lon: float,
    cos_anchor: float,
    lat: float,
    lon: float,
) -> float:
    """Height in metres at ``(lat, lon)`` from a captured height field.

    A pure read, factored out so the projection and the bilinear interpolation
    are unit-tested without a Genesis runtime (the scene build is the only part
    that needs the optional extra).
    """
    dx, dy = _project_local_xy(lat, lon, anchor_lat, anchor_lon, cos_anchor)
    ox, oy = origin_xy_m
    row = (dx - ox) / horizontal_scale_m
    col = (dy - oy) / horizontal_scale_m
    return _bilinear(field, row, col) * vertical_scale_m + base_elevation_m


def _sample_path(
    elevation_fn: Callable[[float, float], float],
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    n: int,
) -> list[tuple[float, float]]:
    """``[(ground_distance_m, elevation_m), ...]`` along the path, both endpoints.

    Same contract and ground-distance metric as ``TerrainModel.path_profile``, so
    the diffraction caller cannot tell the two sources apart.
    """
    count = max(2, int(n))
    total = _ground_distance_m(lat1, lon1, lat2, lon2)
    out: list[tuple[float, float]] = []
    for i in range(count):
        frac = i / (count - 1)
        lat = lat1 + (lat2 - lat1) * frac
        lon = lon1 + (lon2 - lon1) * frac
        out.append((total * frac, elevation_fn(lat, lon)))
    return out


class GenesisWorldSource:
    """A ``WorldSource`` backed by a headless Genesis terrain scene.

    Builds a CPU Genesis scene with a heightfield terrain at construction,
    captures the built height field and its scales, and answers ``elevation`` /
    ``path_profile`` as bilinear reads of that field. Satisfies the
    :class:`~nous.subsystems.terrain.WorldSource` Protocol structurally, so an
    instance passes ``isinstance(src, WorldSource)`` and drops into the comms and
    EO/IR ``terrain=`` seams unchanged.
    """

    def __init__(
        self,
        height_field: Sequence[Sequence[float]] | np.ndarray,
        *,
        horizontal_scale_m: float = 1.0,
        vertical_scale_m: float = 1.0,
        anchor_lat: float = 0.0,
        anchor_lon: float = 0.0,
        origin_xy_m: tuple[float, float] = (0.0, 0.0),
        base_elevation_m: float = 0.0,
        backend: str = "cpu",
        dt: float = 0.01,
        platform_lla: tuple[float, float, float] | None = None,
        platform_velocity_mps: tuple[float, float, float] = (0.0, 0.0, 0.0),
        platform_radius_m: float = 0.5,
    ) -> None:
        field_in = np.asarray(height_field, dtype=np.float32)
        if field_in.ndim != 2 or field_in.size == 0:
            raise ValueError("height_field must be a non-empty 2D array")
        if horizontal_scale_m <= 0.0:
            raise ValueError("horizontal_scale_m must be positive")

        self.anchor_lat = float(anchor_lat)
        self.anchor_lon = float(anchor_lon)
        self._cos_anchor = math.cos(math.radians(anchor_lat))
        self._hs = float(horizontal_scale_m)
        self._vs = float(vertical_scale_m)
        self._origin_xy = (float(origin_xy_m[0]), float(origin_xy_m[1]))
        self._base_m = float(base_elevation_m)

        gs = _import_genesis()
        _ensure_init(gs, backend)
        scene = gs.Scene(
            show_viewer=False,
            rigid_options=gs.options.RigidOptions(dt=float(dt)),
        )
        terrain = scene.add_entity(
            morph=gs.morphs.Terrain(
                horizontal_scale=self._hs,
                vertical_scale=self._vs,
                height_field=field_in,
                pos=(self._origin_xy[0], self._origin_xy[1], self._base_m),
            ),
        )
        self._platform: Any | None = None
        if platform_lla is not None:
            px, py, pz = self._scene_xyz(*platform_lla)
            self._platform = scene.add_entity(
                morph=gs.morphs.Sphere(pos=(px, py, pz), radius=float(platform_radius_m)),
            )
        scene.build()

        self._scene = scene
        self._field = np.asarray(
            terrain.geoms[0].metadata["height_field"], dtype=np.float64
        )
        if self._platform is not None and any(v != 0.0 for v in platform_velocity_mps):
            vx, vy, vz = platform_velocity_mps
            # set_dofs_velocity takes an array_like over the free body's 6 DOFs
            # (3 linear, 3 angular); a numpy array avoids a hard torch import.
            self._platform.set_dofs_velocity(
                velocity=np.asarray([vx, vy, vz, 0.0, 0.0, 0.0], dtype=np.float32)
            )

    def _scene_xyz(self, lat: float, lon: float, alt_m: float) -> tuple[float, float, float]:
        dx, dy = _project_local_xy(
            lat, lon, self.anchor_lat, self.anchor_lon, self._cos_anchor
        )
        return dx, dy, alt_m

    def elevation(self, lat: float, lon: float) -> float:
        """Terrain elevation in metres at ``(lat, lon)``."""
        return _elevation_from_field(
            self._field,
            horizontal_scale_m=self._hs,
            vertical_scale_m=self._vs,
            origin_xy_m=self._origin_xy,
            base_elevation_m=self._base_m,
            anchor_lat=self.anchor_lat,
            anchor_lon=self.anchor_lon,
            cos_anchor=self._cos_anchor,
            lat=lat,
            lon=lon,
        )

    def path_profile(
        self, lat1: float, lon1: float, lat2: float, lon2: float, n: int
    ) -> list[tuple[float, float]]:
        """Sample ``n`` elevations along the path, with ground distances."""
        return _sample_path(self.elevation, lat1, lon1, lat2, lon2, n)

    def step(self, n: int = 1) -> None:
        """Advance the Genesis simulation by ``n`` ticks (drives platform motion)."""
        for _ in range(max(0, int(n))):
            self._scene.step()

    def platform_position(self) -> tuple[float, float, float]:
        """The simulated platform's pose as ``(lat, lon, alt_m)``.

        Inverts the projection used for the terrain, so the position is in the
        same frame the comms and EO/IR seams expect.
        """
        if self._platform is None:
            raise RuntimeError("no platform: construct with platform_lla=... to add one")
        pos = self._platform.get_pos()
        x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
        lat = self.anchor_lat + y / _DEG_TO_M
        lon = self.anchor_lon + x / (_DEG_TO_M * self._cos_anchor)
        return lat, lon, z

    def position_fn(self) -> PositionFn:
        """A ``Callable[[], (lat, lon, alt)]`` for the comms / EO-IR seam."""
        return self.platform_position
