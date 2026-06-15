"""DTN store persistence across a restart (BL-056 increment 4, ADR 0064).

A custodial bundle held by a node must survive a process restart, not just a link
drop: the store is checkpointed to SQLite and restored when a fresh engine is
built on the same database. No network: a tmp sqlite DB via the ``config``
fixture.
"""

from __future__ import annotations

from typing import Any

from nous.config import Settings
from nous.db import StateTransitionLog, init_db
from nous.engine import Engine, _load_profile


def _dtn_profile(config: Settings) -> dict[str, Any]:
    profile = dict(_load_profile(config.profile))
    profile["dtn"] = {
        "self_eid": "dtn://dev/",
        "contacts": [{"a": "dtn://dev/", "b": "dtn://ground/", "up": False}],
    }
    return profile


def test_engine_restart_restores_the_dtn_store(config: Settings) -> None:
    profile = _dtn_profile(config)
    url = config.resolved_db_url()

    first = Engine(
        settings=config,
        profile=profile,
        transition_log=StateTransitionLog(init_db(url)),
        seed=0,
    )
    first.dtn_mesh.originate("dtn://ground/", 100, now_s=0.0, custody=True)
    first.dtn_store.save(first.dtn_mesh.snapshot(first.state.ts_s))

    # A fresh engine on the same database stands in for a process restart.
    second = Engine(
        settings=config,
        profile=profile,
        transition_log=StateTransitionLog(init_db(url)),
        seed=0,
    )
    held = second.dtn_mesh.in_transit()
    assert len(held) == 1
    assert held[0].custody is True
    assert held[0].dest_eid == "dtn://ground/"


def test_disabled_mesh_persists_nothing(config: Settings) -> None:
    # The default profile carries no dtn section, so the mesh is disabled and the
    # store stays empty: a restart restores nothing.
    url = config.resolved_db_url()
    engine = Engine(settings=config, transition_log=StateTransitionLog(init_db(url)))
    assert engine.dtn_mesh.enabled is False
    assert engine.dtn_store.load() is None
