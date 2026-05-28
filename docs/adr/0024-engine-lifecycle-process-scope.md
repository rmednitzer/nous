# ADR 0024: Engine lifecycle is process-scoped, not MCP-session-scoped

- **Status:** Accepted
- **Date:** 2026-05-28
- **Authors:** rmednitzer
- **Builds on:** ADR 0019 (clock/seed seam), AUDIT-2026-05-23 C3

## Context

The simulator engine must advance continuously while the server is up: the
FSM progresses, subsystem physics integrate, and time-based scenario steps
fire on a fixed cadence (`tick_hz`, default 2 Hz). AUDIT-2026-05-23 C3
added a background tick loop driven by the FastMCP server lifespan
(`tick_lifespan`).

That fix is correct for the stdio transport, where one process serves a
single long-lived MCP session, so the server lifespan spans the process.
It is wrong for the HTTP transport that the live deployment uses. The
server is built with `stateless_http=True`, which lets the claude.ai
custom connector open a fresh MCP session per request with no sticky
session state. In stateless mode the MCP SDK creates a new transport and
runs the low-level server once per request
(`StreamableHTTPSessionManager._handle_stateless_request`), so the server
lifespan, and therefore `tick_lifespan`, executes per request:
`engine.start()` (which resets `state.tick` and `ts_s`), one tick, then
`engine.stop()`.

Observed live on `nous-prod-01`: `device_health` pinned at `tick: 1` and
`mode: boot` while `state_history` showed the FSM churning
`reset -> boot -> shutdown` on every tool call, three rows per request in
the `state_transitions` table. The engine was not running as a continuous
simulation; it rebooted on each call.

## Decision

The simulator lifecycle is owned by the server process, not by an MCP
session. The tick loop runs for the process lifetime, decoupled from the
per-request (stateless) MCP session lifecycle.

`build_app()` constructs the `Nous` application (engine plus the audited
FastMCP) and no longer registers the tick loop on the MCP server
lifespan. The serve entrypoint (`nous.cli`) attaches the tick loop to the
process-lifetime ASGI lifespan: for HTTP via `attach_tick_lifespan`,
which composes `tick_lifespan(engine, tick_hz)` around the Starlette app's
own lifespan (the MCP session manager); for stdio by wrapping
`run_stdio_async()` in `tick_lifespan`. The engine is constructed and
started once, ticked by a single background loop, and stopped once at
process shutdown. `stateless_http=True` is retained, so the claude.ai
connector is unaffected.

## Consequences

The engine advances continuously regardless of request traffic, the FSM
progresses, and the per-request `reset/boot/shutdown` churn (and its
database write amplification) is gone. The MCP session lifecycle (per
request, stateless) and the simulator lifecycle (per process) are now
independent concerns, which is the correct model for a long-running
physical-system simulation exposed over a stateless API.

The cost is that the serve path no longer calls `FastMCP.run(...)`; it
builds the ASGI app and runs uvicorn (HTTP) or `run_stdio_async` (stdio)
directly so it can own the process lifespan. `build_server()` is retained
as a thin `build_app(...).mcp` accessor for tests and embedders.

Switching to stateful HTTP (`stateless_http=False`) was rejected: it would
make the server lifespan process-scoped again, but stateful sessions
complicate the claude.ai connector and the Caddy front end for no benefit
here, since the simulator needs no MCP session affinity.

## Revisit triggers

A future MCP SDK that runs the configured server lifespan once per process
even in stateless mode would let the tick loop move back onto the server
lifespan. Running multiple server workers (for example gunicorn) would
mean multiple engines; the simulator would then need one shared engine
process, or a single designated ticking worker, which this ADR's
process-scope assumption would no longer satisfy on its own.
