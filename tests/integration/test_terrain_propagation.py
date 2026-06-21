"""Engine-level test of BL-089 terrain diffraction via the terrain-demo profile.

Drives the shipped ``profiles/terrain-demo.yaml`` through the engine: the relay
link opts into terrain, so the link budget samples the procedural world along the
path to the relay each tick and runs multi-edge Bullington diffraction over it. A
ridge between the device and the relay degrades the link where the single
knife-edge model would not, and the whole pipeline (terrain sample to link budget
to observation to ``derive`` to FSM) runs on the real artifacts.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from nous.engine import Engine, _load_profile
from nous.subsystems.comms import Link


def _profile_with_relay(
    overrides: dict[str, Any], *, drop_world: bool = False
) -> dict[str, Any]:
    profile = copy.deepcopy(dict(_load_profile("terrain-demo")))
    profile["comms"]["links"][0]["propagation"].update(overrides)
    if drop_world:
        profile.pop("world", None)
    return profile


def _solved_relay(profile: dict[str, Any]) -> Link:
    eng = Engine(profile=profile, seed=7)
    eng.start()
    eng.position.set_position(47.0, 13.0, alt_m=460.0)
    for _ in range(3):
        eng.tick()
    link = eng.comms.link("relay")
    assert link is not None
    return link


def test_terrain_diffraction_degrades_the_link(tmp_nous_home: Path) -> None:
    terrain_on = _solved_relay(_profile_with_relay({}))
    terrain_off = _solved_relay(_profile_with_relay({"use_terrain": False}))
    assert terrain_on.path_loss_db is not None and terrain_off.path_loss_db is not None
    # The ridge adds tens of dB of diffraction loss that flow through to the link.
    assert terrain_on.path_loss_db > terrain_off.path_loss_db
    assert terrain_on.capacity_bps < terrain_off.capacity_bps
    assert terrain_on.loss_pct > terrain_off.loss_pct


def test_no_world_section_keeps_single_knife_edge(tmp_nous_home: Path) -> None:
    # Reduces-to-prior: with no world section the use_terrain flag is inert (no
    # terrain model to sample), so the link matches the use_terrain-off budget.
    no_world = _solved_relay(_profile_with_relay({}, drop_world=True))
    terrain_off = _solved_relay(
        _profile_with_relay({"use_terrain": False}, drop_world=True)
    )
    assert no_world.path_loss_db == pytest.approx(terrain_off.path_loss_db)
    assert no_world.capacity_bps == pytest.approx(terrain_off.capacity_bps)


def test_terrain_loss_varies_with_device_position(tmp_nous_home: Path) -> None:
    # Moving the device changes the sampled path, so the terrain diffraction (and
    # the total path loss) varies position to position, not a fixed offset.
    eng = Engine(profile=_load_profile("terrain-demo"), seed=7)
    eng.start()
    losses: list[float] = []
    for lon in (13.0, 13.01, 13.02, 13.03):
        eng.position.set_position(47.0, lon, alt_m=460.0)
        for _ in range(2):
            eng.tick()
        link = eng.comms.link("relay")
        assert link is not None and link.path_loss_db is not None
        losses.append(link.path_loss_db)
    assert len({round(x, 3) for x in losses}) > 1
