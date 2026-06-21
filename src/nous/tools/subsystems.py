"""Subsystem telemetry reads (ADR 0021) plus the comms write tools (ADR 0033).

The ten read-only (T0) subsystem status tools, grouped into one module per
the capability-grouping option of ADR 0021's revisit trigger: they are uniform
telemetry reads (truth plus calibrated estimate), so one ``subsystems`` module
is more legible than ten one-tool files. The comms write tools (``comms_send`` /
``comms_publish``, T2, ADR 0033) live here too, alongside the store-and-forward
outbox surface (``comms_enqueue`` / ``comms_flush``, T2, and the ``comms_outbox``
read, T0; BL-077, ADR 0047), so every comms tool is discoverable in one place.
(``inference_status`` stays with ``inference_local`` in the inference module.)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from ..server import Nous, WrapFn
    from ..types import Estimate


def _rejected_from_health(estimate: Estimate) -> int:
    """Rejection count from the estimate's health block, not a bare attribute.

    Reading the diagnostic through the Protocol's ``state()`` return (where ADR
    0045 placed it) rather than ``estimator.rejected_updates`` keeps a future
    Protocol-conforming estimator that omits that attribute from breaking this
    T0 read (audit 2026-06-14b MED-3, ADR 0058). ``health`` is optional on the
    contract, so an estimator that reports none counts as zero rejections.
    """
    health = estimate.health
    return health.rejected_updates if health is not None else 0


def register(mcp: FastMCP, app: Nous, wrap: WrapFn) -> None:
    """Register the subsystem telemetry reads on ``mcp``."""

    @mcp.tool()
    async def power_status(ctx: Context | None = None) -> str:
        """Battery state-of-charge, draw, projected endurance."""

        async def _work() -> str:
            truth = dict(app.engine.power.truth())
            estimate = app.engine.power_est.state()
            payload = {
                "soc_pct": round(truth["soc_pct"], 3),
                "voltage_v": round(truth["voltage_v"], 3),
                "current_a": round(truth["current_a"], 4),
                "load_w": round(truth["load_w"], 3),
                "charge_offered_w": round(truth["charge_offered_w"], 3),
                "charge_accepted_w": round(truth["charge_accepted_w"], 3),
                "remaining_wh": round(truth["remaining_wh"], 3),
                "endurance_min_p50": (
                    None
                    if truth["endurance_min"] is None
                    else round(truth["endurance_min"], 2)
                ),
                "flag": truth["flag"],
                "estimate": {
                    "soc_pct": round(estimate.point["soc_pct"], 3),
                    "soc_pct_sigma": round(
                        estimate.covariance["soc_pct"] ** 0.5, 4
                    ),
                    "voltage_v": round(estimate.point["voltage_v"], 3),
                },
            }
            return json.dumps(payload)

        return await wrap("power_status", {}, ctx, _work)

    @mcp.tool()
    async def apu_status(ctx: Context | None = None) -> str:
        """Auxiliary-power-unit state (solar, fuel cell, vehicle, USB-C PD)."""

        async def _work() -> str:
            truth = dict(app.engine.apu.truth())
            estimate = app.engine.apu_est.state()
            payload = {
                "solar_w": round(truth["solar_w"], 3),
                "fuelcell_w": round(truth["fuelcell_w"], 3),
                "vehicle_w": round(truth["vehicle_w"], 3),
                "usbc_w": round(truth["usbc_w"], 3),
                "total_w": round(truth["total_w"], 3),
                "fuelcell_fuel_g": round(truth["fuel_g"], 3),
                "fuelcell_fuel_pct": round(truth["fuel_pct"], 3),
                "vehicle_connected": truth["vehicle_connected"],
                "usbc_connected": truth["usbc_connected"],
                "usbc_profile_w": round(truth["usbc_profile_w"], 3),
                "estimate": {
                    "total_w": round(estimate.point["total_w"], 3),
                    "total_w_sigma": round(
                        estimate.covariance["total_w"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await wrap("apu_status", {}, ctx, _work)

    @mcp.tool()
    async def thermal_status(ctx: Context | None = None) -> str:
        """Two-state thermal model (junction + enclosure + ambient)."""

        async def _work() -> str:
            truth = dict(app.engine.thermal.truth())
            estimate = app.engine.thermal_est.state()
            payload = {
                "junction_c": round(truth["junction_c"], 3),
                "enclosure_c": round(truth["enclosure_c"], 3),
                "ambient_c": round(truth["ambient_c"], 3),
                "load_w": round(truth["load_w"], 3),
                "headroom_c": round(truth["headroom_c"], 3),
                "throttling": truth["throttling"],
                "junction_temp_throttle": round(truth["junction_temp_throttle"], 3),
                "junction_temp_max": round(truth["junction_temp_max"], 3),
                "estimate": {
                    "junction_c": round(estimate.point["junction_c"], 3),
                    "junction_c_sigma": round(
                        estimate.covariance["junction_c"] ** 0.5, 4
                    ),
                    "enclosure_c": round(estimate.point["enclosure_c"], 3),
                    "enclosure_c_sigma": round(
                        estimate.covariance["enclosure_c"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await wrap("thermal_status", {}, ctx, _work)

    @mcp.tool()
    async def compute_status(ctx: Context | None = None) -> str:
        """Compute subsystem: load fraction, electrical draw, throttling."""

        async def _work() -> str:
            truth = dict(app.engine.compute.truth())
            estimate = app.engine.compute_est.state()
            payload = {
                "load_pct": round(truth["load_pct"], 3),
                "requested_load_pct": round(truth["requested_load_pct"], 3),
                "draw_w": round(truth["draw_w"], 3),
                "draw_w_idle": round(truth["draw_w_idle"], 3),
                "draw_w_load": round(truth["draw_w_load"], 3),
                "throttled": truth["throttled"],
                "saturated": truth["saturated"],
                "tok_per_s_capacity": round(truth["tok_per_s_capacity"], 3),
                "estimate": {
                    "load_pct": round(estimate.point["load_pct"], 3),
                    "load_pct_sigma": round(
                        estimate.covariance["load_pct"] ** 0.5, 4
                    ),
                    "draw_w": round(estimate.point["draw_w"], 3),
                    "draw_w_sigma": round(
                        estimate.covariance["draw_w"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await wrap("compute_status", {}, ctx, _work)

    @mcp.tool()
    async def storage_status(ctx: Context | None = None) -> str:
        """Storage subsystem: capacity, used, wear, write rate."""

        async def _work() -> str:
            truth = dict(app.engine.storage.truth())
            estimate = app.engine.storage_est.state()
            payload = {
                "capacity_gib": round(truth["capacity_gib"], 3),
                "used_gib": round(truth["used_gib"], 3),
                "free_gib": round(truth["free_gib"], 3),
                "used_pct": round(truth["used_pct"], 3),
                "wear_pct": round(truth["wear_pct"], 4),
                "lifetime_physical_gib": round(truth["lifetime_physical_gib"], 3),
                "write_rate_gib_per_s": round(truth["write_rate_gib_per_s"], 4),
                "at_capacity": truth["at_capacity"],
                "worn_out": truth["worn_out"],
                "estimate": {
                    "used_gib": round(estimate.point["used_gib"], 3),
                    "used_gib_sigma": round(
                        estimate.covariance["used_gib"] ** 0.5, 4
                    ),
                    "wear_pct": round(estimate.point["wear_pct"], 4),
                    "wear_pct_sigma": round(
                        estimate.covariance["wear_pct"] ** 0.5, 4
                    ),
                },
            }
            return json.dumps(payload)

        return await wrap("storage_status", {}, ctx, _work)

    @mcp.tool()
    async def comms_state(ctx: Context | None = None) -> str:
        """Comms-stack summary (per ADR-0006)."""

        async def _work() -> str:
            label, reason = app.engine.comms.derive_state()
            links = [link.model_dump() for link in app.engine.comms.link_estimates()]
            return json.dumps(
                {
                    "state": label.value,
                    "reason": reason,
                    "links": links,
                }
            )

        return await wrap("comms_state", {}, ctx, _work)

    @mcp.tool()
    async def comms_status(ctx: Context | None = None) -> str:
        """Comms subsystem: per-link envelope, RSSI, loss, throughput, age, age-out count/time."""

        async def _work() -> str:
            truth = dict(app.engine.comms.truth())
            label, reason = app.engine.comms.derive_state()
            payload = {
                "state": label.value,
                "reason": reason,
                "link_count": len(truth["links"]),
                "links": truth["links"],
            }
            return json.dumps(payload)

        return await wrap("comms_status", {}, ctx, _work)

    @mcp.tool()
    async def comms_send(link_id: str, n_bytes: int, ctx: Context | None = None) -> str:
        """Record a transmission of ``n_bytes`` on link ``link_id`` (T2, ADR 0033).

        Wraps the comms subsystem's ``tx`` seam: a successful send resets the
        link's age-out timer (keeping it live) and updates its coarse
        throughput. A send on an unknown link, a link the controller has forced
        down, or a non-positive byte count is rejected. When the active EMCON
        profile forbids emitting on the link (BL-060 / ADR 0065, or its scheduled
        window is closed under ADR 0066), the bytes are
        held in the store-and-forward outbox (``reason`` ``emcon``) instead of
        dropped, so they ship when emissions resume. Returns ``{"ok": bool,
        "link_id": str, "bytes_accepted": int, "connected": bool}``; ``ok`` is
        ``false`` when no bytes were accepted. A non-EMCON failure adds
        ``reason`` naming the cause (the link's ``last_tx_reason``:
        ``forced_down`` / ``no_capacity`` / ``empty``, or ``unknown_link``;
        BL-109). An EMCON defer adds ``reason``
        (``emcon``), ``emcon_profile``, and ``enqueued`` (whether the outbox
        took the held bytes); ``connected`` still reflects the link's real
        ``is_live`` health, since EMCON is orthogonal to connectivity. Tier T2
        (stateful): the link's live state changes and the call is audited.
        """

        async def _work() -> str:
            engine = app.engine
            now_s = engine.state.ts_s
            link = engine.comms.link(link_id)
            if (
                link is not None
                and n_bytes > 0
                and not engine.comms.emcon.permits(link_id, now_s=now_s)
            ):
                held = engine.outbox.enqueue(
                    link_id, int(n_bytes), now_s=now_s, kind="emcon_deferred"
                )
                return json.dumps(
                    {
                        "ok": False,
                        "link_id": link_id,
                        "bytes_accepted": 0,
                        "reason": "emcon",
                        "emcon_profile": engine.comms.emcon.active,
                        "enqueued": held.accepted,
                        "connected": bool(link.is_live()),
                    }
                )
            accepted = engine.comms.tx(link_id, n_bytes, now_s=now_s)
            link = engine.comms.link(link_id)
            body: dict[str, Any] = {
                "ok": accepted > 0,
                "link_id": link_id,
                "bytes_accepted": accepted,
                "connected": bool(link.is_live()) if link is not None else False,
            }
            if accepted <= 0:
                from .publish import tx_failure_reason

                body["reason"] = tx_failure_reason(engine, link_id)
            return json.dumps(body)

        return await wrap(
            "comms_send", {"link_id": link_id, "n_bytes": n_bytes}, ctx, _work
        )

    @mcp.tool()
    async def comms_publish(
        link_id: str,
        adapter: str,
        data: dict[str, Any] | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Encode ``data`` via an interop adapter and transmit it on a link (T2, ADR 0033).

        Combines the interop registry (BL-041) with the comms ``tx`` seam: the
        message is encoded to wire bytes through the named adapter (``cot``,
        ``nmea0183``, ...), then those bytes are accounted against the link's
        envelope (age reset, throughput updated). The encoded payload is
        returned hex-encoded alongside the byte count the link accepted, so a
        controller sees both the wire form and its effect on the link.

        Encode errors carry the same categories as ``interop_encode`` (unknown
        adapter, stale source estimate, schema/value error) but are reported as
        ``{"ok": false, ...}`` so the result shape stays uniform with
        ``comms_send``; nothing is transmitted on an encode failure. Tier T2
        (stateful).
        """

        async def _work() -> str:
            from .publish import encode_and_tx

            return json.dumps(
                encode_and_tx(app.engine, link_id, adapter, dict(data or {}))
            )

        return await wrap(
            "comms_publish",
            {"link_id": link_id, "adapter": adapter, "data": dict(data or {})},
            ctx,
            _work,
        )

    @mcp.tool()
    async def comms_enqueue(
        link_id: str,
        n_bytes: int | None = None,
        payload_hex: str | None = None,
        precedence: str = "routine",
        kind: str = "raw",
        ttl_s: float | None = None,
        dest_eid: str | None = None,
        bundle_id: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Queue a package for store-and-forward when comms are degraded (T2, BL-077).

        The fire-and-forget ``comms_send`` / ``comms_publish`` path drops a
        transmission the moment the link cannot carry it. ``comms_enqueue``
        instead holds the package in a bounded, precedence-ordered outbox and the
        tick loop delivers it (and ``comms_flush`` forces a drain) when the link
        recovers. Give the bytes either as a raw ``n_bytes`` count or as a
        ``payload_hex`` blob (e.g. the ``payload_hex`` an ``interop_encode`` call
        returned); ``payload_hex`` is authoritative for the size when both are
        present.

        ``precedence`` is military message precedence (``routine`` < ``priority``
        < ``immediate`` < ``flash``); a scarce link flushes the highest first and
        a package is only ever evicted to make room for a strictly
        higher-precedence one. ``ttl_s`` overrides the profile's default
        time-to-live; an expired package is dropped rather than shipped stale.

        Each package carries a BPv7-shaped bundle identity (ADR 0061): pass
        ``dest_eid`` to set the destination endpoint (else the profile's peer) and
        ``bundle_id`` to make the call idempotent, so a re-submission of a
        still-queued or recently-delivered id is refused as a duplicate rather
        than queued twice. The returned ``package.bundle`` block carries the
        assigned id.

        Returns ``{"ok": bool, "reason": str, "package": {...}, "evicted":
        [ids], "depth": N}``; ``ok`` is false when the package is empty, larger
        than the outbox budget, refused because the queue is full of
        equal-or-higher-precedence traffic, or recognised as a duplicate bundle.
        Tier T2 (stateful).
        """

        async def _work() -> str:
            from ..state.comms_outbox import Precedence
            from ._errors import error_class

            payload: bytes | None = None
            size: int
            if payload_hex is not None:
                try:
                    payload = bytes.fromhex(payload_hex)
                except ValueError as exc:
                    return json.dumps({"ok": False, "reason": f"hex: {error_class(exc)}"})
                size = len(payload)
            elif n_bytes is not None:
                size = int(n_bytes)
            else:
                return json.dumps(
                    {"ok": False, "reason": "provide n_bytes or payload_hex"}
                )

            result = app.engine.outbox.enqueue(
                link_id,
                size,
                now_s=app.engine.state.ts_s,
                precedence=Precedence.parse(precedence),
                kind=kind,
                ttl_s=ttl_s,
                payload=payload,
                dest_eid=dest_eid,
                bundle_id=bundle_id,
            )
            body = result.to_dict()
            body["ok"] = result.accepted
            body["depth"] = app.engine.outbox.depth()
            return json.dumps(body)

        return await wrap(
            "comms_enqueue",
            {
                "link_id": link_id,
                "n_bytes": n_bytes,
                "payload_hex_len": len(payload_hex or ""),
                "precedence": precedence,
                "kind": kind,
                "ttl_s": ttl_s,
                "dest_eid": dest_eid,
                "bundle_id": bundle_id,
            },
            ctx,
            _work,
        )

    @mcp.tool()
    async def comms_outbox(ctx: Context | None = None) -> str:
        """Read the store-and-forward outbox: depth, triage breakdown, counters (T0, BL-077).

        Reports the queue depth and bytes pending, the per-precedence and
        per-link breakdown, the head package a flush would deliver first (with
        its remaining time-to-live), the cumulative disposition counters
        (enqueued / delivered / dropped_overflow / expired / rejected / deduped)
        and the per-cause defer breakdown (``defer_causes``: why a flush held a
        package, keyed link_down / loss / emcon / no_capacity; BL-108), and the
        packages in triage (flush) order. The package list is capped so the read
        stays bounded; ``packages_truncated`` flags when the queue is deeper than
        the listing.
        """

        async def _work() -> str:
            outbox = app.engine.outbox
            now_s = app.engine.state.ts_s
            body = outbox.status(now_s=now_s)
            listed = outbox.packages()
            cap = 25
            body["packages"] = [pkg.to_dict() for pkg in listed[:cap]]
            body["packages_truncated"] = len(listed) > cap
            return json.dumps(body)

        return await wrap("comms_outbox", {}, ctx, _work)

    @mcp.tool()
    async def comms_flush(
        link_id: str | None = None,
        max_bytes: int | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Force a triage-ordered drain of the outbox against the live links (T2, BL-077).

        Walks queued packages by descending precedence then enqueue order,
        delivering each through the comms ``tx`` seam on a live link. ``link_id``
        restricts the drain to one link (others are left queued); ``max_bytes``
        caps the bytes delivered per link this call (unbounded when omitted). A
        package whose link is down, or that does not fit the remaining budget,
        stays queued, and expired packages are dropped rather than shipped.
        Returns the delivered / deferred / expired package ids plus the resulting
        outbox depth. Tier T2 (stateful): links are accounted and the call is
        audited.
        """

        async def _work() -> str:
            outbox = app.engine.outbox
            link_budget: dict[str, float] | None = None
            if link_id is not None or max_bytes is not None:
                cap = float(max_bytes) if max_bytes is not None else float("inf")
                link_budget = {}
                for lid in app.engine.comms.link_ids:
                    if link_id is not None and lid != link_id:
                        link_budget[lid] = 0.0
                    else:
                        link_budget[lid] = cap
            result = outbox.flush(
                app.engine.comms,
                now_s=app.engine.state.ts_s,
                link_budget_bytes=link_budget,
            )
            body = result.to_dict()
            body["ok"] = True
            body["depth"] = outbox.depth()
            body["queued_bytes"] = outbox.queued_bytes()
            return json.dumps(body)

        return await wrap(
            "comms_flush",
            {"link_id": link_id, "max_bytes": max_bytes},
            ctx,
            _work,
        )

    @mcp.tool()
    async def emcon_status(ctx: Context | None = None) -> str:
        """Read the EMCON emission posture: active profile and permitted links (T0, BL-060).

        EMCON (emission control, ADR 0065) is an operator-imposed posture that
        gates which comms links the device may emit on, orthogonal to physical
        link health. Returns the active profile, whether a ``comms.emcon`` profile
        section configured it, ``default_requested`` / ``default_valid`` (which
        distinguish an operator who chose ``unrestricted`` from one whose
        configured ``default`` named an unknown profile and was rejected back to
        ``unrestricted``), the links the active profile permits, and every
        available profile with its permitted links, plus any duty-cycle emission
        ``window`` on a profile and whether the active posture is ``emitting``
        right now (ADR 0066), and any ``minimize`` policy that coarsens emitted
        metadata under a profile (ADR 0067). ``unrestricted`` (all links)
        and ``silent`` (none) are always present; with no ``comms.emcon`` section
        the posture is ``unrestricted`` and inert.
        """

        async def _work() -> str:
            return json.dumps(app.engine.comms.emcon.status(now_s=app.engine.state.ts_s))

        return await wrap("emcon_status", {}, ctx, _work)

    @mcp.tool()
    async def emcon_set(profile: str, ctx: Context | None = None) -> str:
        """Set the active EMCON emission profile (T2, BL-060 / ADR 0065).

        Activates a named emission profile, changing which links the device may
        emit on from this tick forward. ``silent`` imposes full radio silence,
        ``unrestricted`` lifts EMCON, and a profile-defined name permits its
        subset, inside its duty-cycle burst window if it defines one (ADR 0066).
        While a profile forbids a link, a ``comms_send`` / ``comms_publish``
        / ``self_model_publish`` on it is held in the store-and-forward outbox
        rather than dropped, and the tick-driven drain ships the backlog once the
        posture is lifted. Returns ``{"ok": bool, "reason": str, ...}`` with the
        new posture; ``ok`` is false, and nothing changes, for an unknown profile.
        Tier T2 (stateful).
        """

        async def _work() -> str:
            emcon = app.engine.comms.emcon
            ok = emcon.set_profile(profile)
            body = emcon.status(now_s=app.engine.state.ts_s)
            body["ok"] = ok
            body["reason"] = "" if ok else f"unknown profile {profile}"
            return json.dumps(body)

        return await wrap("emcon_set", {"profile": profile}, ctx, _work)

    @mcp.tool()
    async def dtn_mesh(ctx: Context | None = None) -> str:
        """Read the DTN mesh: nodes, contacts, in-transit bundles, counters (T0, BL-056).

        The delay-tolerant-networking overlay (ADR 0062, ADR 0063, ADR 0064, ADR 0068)
        routes bundles across a configured multi-node topology with store-and-forward and
        custody transfer, using contact-graph routing over the contacts'
        schedules. Returns the self EID, the acknowledgement-loss percentage, the
        per-node held-bundle counts and the per-node store cap (``max_store``,
        ADR 0068), the contact graph (up/down, rate, loss, and the optional
        ``start_s`` / ``end_s`` window), the in-transit total, the cumulative
        disposition counters (originated / delivered / forwarded / retransmits /
        dropped / expired / deduped / restore_lost) and the per-cause drop
        breakdown (``drop_causes``: max_hops / forward_loss / retry_exhausted /
        store_overflow; a within-process attribution, so it restarts from a fresh
        process while ``dropped`` carries forward; BL-108), and the in-transit
        bundles
        grouped by holding node, each node's bundles in triage (forward) order
        (capped so the read stays bounded; ``bundles_truncated`` flags a deeper
        backlog), and a ``persistence`` block reporting whether the store is
        SQLite-backed and so survives a restart (ADR 0064). With no ``dtn``
        section in the profile the mesh is disabled: ``enabled`` is false and the
        topology, bundles, and counters are empty.
        """

        async def _work() -> str:
            mesh = app.engine.dtn_mesh
            body = mesh.status()
            listed = mesh.in_transit()
            cap = 25
            body["bundles"] = [bundle.to_dict() for bundle in listed[:cap]]
            body["bundles_truncated"] = len(listed) > cap
            body["persistence"] = app.engine.dtn_store.status()
            return json.dumps(body)

        return await wrap("dtn_mesh", {}, ctx, _work)

    @mcp.tool()
    async def dtn_send(
        dest_eid: str,
        n_bytes: int = 1024,
        precedence: str = "routine",
        custody: bool = False,
        lifetime_s: float | None = None,
        bundle_id: str | None = None,
        ctx: Context | None = None,
    ) -> str:
        """Originate a bundle at the device node toward a remote EID (T2, BL-056).

        Injects a bundle into the DTN mesh (ADR 0062, ADR 0063) bound for
        ``dest_eid``; the tick loop routes it along the earliest-arrival
        contact-graph path toward the destination, storing it at each hop while a
        contact is down or its scheduled window has not opened. ``custody``
        requests reliable delivery: a custodial bundle is retained and
        retransmitted on a lost forward or a lost custody acknowledgement rather
        than dropped, up to the profile's retry bound, and any duplicate the
        retransmission creates is deduplicated. ``precedence`` is military message
        precedence (the mesh forwards the highest first), ``lifetime_s`` overrides
        the default bundle lifetime, and ``bundle_id`` names the bundle. Returns
        the assigned bundle, or an error when the mesh is disabled (no ``dtn``
        profile section) or the size is non-positive. Tier T2 (stateful).
        """

        async def _work() -> str:
            from ..state.comms_outbox import Precedence

            mesh = app.engine.dtn_mesh
            bundle = mesh.originate(
                dest_eid,
                int(n_bytes),
                now_s=app.engine.state.ts_s,
                precedence=Precedence.parse(precedence),
                custody=bool(custody),
                lifetime_s=lifetime_s,
                bundle_id=bundle_id,
            )
            if bundle is None:
                reason = (
                    "dtn mesh disabled (no dtn profile section)"
                    if not mesh.enabled
                    else "non-positive size"
                )
                return json.dumps({"ok": False, "reason": reason})
            return json.dumps(
                {
                    "ok": True,
                    "bundle": bundle.to_dict(),
                    "in_transit": len(mesh.in_transit()),
                }
            )

        return await wrap(
            "dtn_send",
            {
                "dest_eid": dest_eid,
                "n_bytes": n_bytes,
                "precedence": precedence,
                "custody": custody,
                "lifetime_s": lifetime_s,
                "bundle_id": bundle_id,
            },
            ctx,
            _work,
        )

    @mcp.tool()
    async def position_status(ctx: Context | None = None) -> str:
        """Position subsystem: lat/lon/alt ground truth, fix state, drift."""

        async def _work() -> str:
            truth = dict(app.engine.position.truth())
            estimate = app.engine.position_est.state()
            payload = {
                "lat": round(truth["lat"], 6),
                "lon": round(truth["lon"], 6),
                "alt_m": round(truth["alt_m"], 3),
                "speed_mps": round(truth["speed_mps"], 3),
                "heading_deg": round(truth["heading_deg"], 3),
                "vertical_mps": round(truth["vertical_mps"], 3),
                "has_fix": truth["has_fix"],
                "dead_reckoning_s": round(truth["dead_reckoning_s"], 3),
                "fix_rate_hz": round(truth["fix_rate_hz"], 3),
                "estimate": {
                    "lat": round(estimate.point.get("lat", 0.0), 6),
                    "lon": round(estimate.point.get("lon", 0.0), 6),
                    "alt_m": round(estimate.point.get("alt_m", 0.0), 3),
                    "lat_sigma": round(
                        estimate.covariance.get("lat", 0.0) ** 0.5, 8
                    ),
                    "lon_sigma": round(
                        estimate.covariance.get("lon", 0.0) ** 0.5, 8
                    ),
                    "alt_sigma_m": round(
                        estimate.covariance.get("alt_m", 0.0) ** 0.5, 4
                    ),
                    "rejected_updates": _rejected_from_health(estimate),
                },
            }
            return json.dumps(payload)

        return await wrap("position_status", {}, ctx, _work)

    @mcp.tool()
    async def sensors_status(ctx: Context | None = None) -> str:
        """Environmental sensor pack: ambient temp, humidity, baro pressure."""

        async def _work() -> str:
            truth = dict(app.engine.sensors.truth())
            estimate = app.engine.sensors_est.state()
            payload = {
                "temp_c": round(truth["temp_c"], 3),
                "humidity_pct": round(truth["humidity_pct"], 3),
                "baro_kpa": round(truth["baro_kpa"], 3),
                "estimate": {
                    "temp_c": round(estimate.point.get("temp_c", 0.0), 3),
                    "temp_c_sigma": round(
                        estimate.covariance.get("temp_c", 0.0) ** 0.5, 4
                    ),
                    "humidity_pct": round(
                        estimate.point.get("humidity_pct", 0.0), 3
                    ),
                    "humidity_pct_sigma": round(
                        estimate.covariance.get("humidity_pct", 0.0) ** 0.5, 4
                    ),
                    "baro_kpa": round(estimate.point.get("baro_kpa", 0.0), 3),
                    "baro_kpa_sigma": round(
                        estimate.covariance.get("baro_kpa", 0.0) ** 0.5, 4
                    ),
                    "rejected_updates": _rejected_from_health(estimate),
                },
            }
            return json.dumps(payload)

        return await wrap("sensors_status", {}, ctx, _work)

    @mcp.tool()
    async def biometrics_status(ctx: Context | None = None) -> str:
        """Operator biometrics: heart rate, core temp, hydration, cognitive load."""

        async def _work() -> str:
            truth = dict(app.engine.biometrics.truth())
            estimate = app.engine.biometrics_est.state()
            payload = {
                "heart_rate_bpm": round(truth["heart_rate_bpm"], 2),
                "core_temp_c": round(truth["core_temp_c"], 3),
                "hydration_pct": round(truth["hydration_pct"], 2),
                "cognitive_load": round(truth["cognitive_load"], 3),
                "estimate": {
                    "heart_rate_bpm": round(
                        estimate.point.get("heart_rate_bpm", 0.0), 2
                    ),
                    "heart_rate_bpm_sigma": round(
                        estimate.covariance.get("heart_rate_bpm", 0.0) ** 0.5, 3
                    ),
                    "core_temp_c": round(estimate.point.get("core_temp_c", 0.0), 3),
                    "core_temp_c_sigma": round(
                        estimate.covariance.get("core_temp_c", 0.0) ** 0.5, 4
                    ),
                    "hydration_pct": round(
                        estimate.point.get("hydration_pct", 0.0), 2
                    ),
                    "hydration_pct_sigma": round(
                        estimate.covariance.get("hydration_pct", 0.0) ** 0.5, 3
                    ),
                    "cognitive_load": round(
                        estimate.point.get("cognitive_load", 0.0), 3
                    ),
                    "cognitive_load_sigma": round(
                        estimate.covariance.get("cognitive_load", 0.0) ** 0.5, 4
                    ),
                    "rejected_updates": _rejected_from_health(estimate),
                },
            }
            return json.dumps(payload)

        return await wrap("biometrics_status", {}, ctx, _work)
