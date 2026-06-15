"""DTN store persistence across a restart (BL-056 increment 4, ADR 0064).

A custodial bundle held by a node must survive a process restart, not just a link
drop: the store is checkpointed to SQLite and restored when a fresh engine is
built on the same database. No network: a tmp sqlite DB via the ``config``
fixture.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from nous.config import Settings
from nous.db import DtnMetaRow, DtnStore, StateTransitionLog, init_db
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


def test_load_degrades_on_a_corrupt_ledger(config: Settings) -> None:
    # A corrupt JSON ledger must not raise out of load(): it degrades to None.
    db = init_db(config.resolved_db_url())
    store = DtnStore(db)
    with Session(db) as session:
        session.add(
            DtnMetaRow(
                id=1, ts_s=0.0, next_seq=1, node_seen="not json", delivered_ids="[]"
            )
        )
        session.commit()
    assert store.load() is None
    assert store.degraded is True
    # AUDIT-2026-06-15 M-1 / BL-101: a corrupt restore is a read fault, not a
    # write fault. It must not inflate the save counters; a controller reads the
    # distinct load fields to tell a read fault from a write fault.
    assert store.load_failures == 1
    assert store.last_load_error != ""
    assert store.save_failures == 0
    assert store.last_error == ""
    snapshot = store.status()
    assert snapshot["load_failures"] == 1
    assert snapshot["save_failures"] == 0
    assert snapshot["last_load_error"] == store.last_load_error


def test_engine_threads_db_init_error_to_the_dtn_store(config: Settings) -> None:
    # A configured-but-failed DB must show degraded DTN persistence, not healthy.
    log = StateTransitionLog(None, init_error="OperationalError")
    engine = Engine(settings=config, transition_log=log)
    assert engine.dtn_store.init_error == "OperationalError"
    assert engine.dtn_store.degraded is True
