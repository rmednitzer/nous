# ADR 0021: Per-subsystem MCP tool modules

- **Status:** Accepted
- **Date:** 2026-05-24
- **Authors:** rmednitzer
- **Builds on:** ADR 0001, ADR 0007, ADR 0013

## Context

`src/nous/server.py` is 661 lines and registers nineteen
`@mcp.tool()` callbacks against a single FastMCP instance. The
functions are organised by alphabetical proximity rather than by
subsystem, so adding a tool that reads a new estimator requires
scanning the file for the right neighbour. The tier classifier in
`policy.py` lists the same nineteen names as four frozensets that have
to stay in sync with `server.py` by hand.

The repo's existing seams are already per-subsystem:
`src/nous/subsystems/{power,thermal,...}.py`, the parallel directory
under `estimators/`, the `Subsystem` and `Estimator` Protocols, the
matching docs under `docs/subsystems/`. The tool surface is the only
layer that breaks the per-subsystem decomposition.

The pattern the public surface should follow is "the tool layer mirrors
the model decomposition." Today's `server.py` does not: ten subsystems,
one tool file. The audited-runner wrapping is centralised (which is
correct); only the per-subsystem grouping of handlers is missing.

This is also a forward-looking concern: BL-014 (scenario loader) and
BL-018 (self-model wiring) will each want their own tools.  Adding
them to the existing `server.py` pushes the file past the size where
a single screen captures the wiring.

## Decision

Move tool definitions into per-subsystem modules under
`src/nous/tools/`:

```
src/nous/tools/
  __init__.py        register(mcp) helper
  meta.py            device_info, device_health, interop_formats
  power.py           power_status
  apu.py             apu_status
  thermal.py         (when added)
  compute.py         compute_status
  ...
  self_model.py      self_model_assess, self_estimator_status
  state.py           state_get, state_history
  inference.py       inference_local
  interop.py         interop_encode, interop_decode
```

Each module exports a `register(mcp: FastMCP) -> None` that decorates
its own handlers against the shared `mcp` instance. `server.py` keeps
the lifespan, the `Nous` orchestrator, and the audited-runner wiring;
the file shrinks to roughly the size of `engine.py`.

Tier classification stays centralised in `policy.py`. The frozensets
get a small audit-time check (a unit test that walks
`mcp._tools` and asserts every registered tool name appears in
exactly one frozenset). The additive-surface rule in ADR-0007 keeps
its default: an unknown tool name classifies as `STATEFUL`.

The audited-runner wrapping pattern stays as today's `_wrap()` +
`audited_run()`. Each per-subsystem module imports the helper and
threads it through every handler; no handler bypasses the runner.

## Consequences

Easier: a new subsystem ships with its tools next to its physics and
estimator code; the diff that adds it is one folder plus a one-line
edit to `tools/__init__.py`. Reviewing the audited-runner wrapping is
mechanical (one grep per module). The tier-classifier coverage
becomes a unit test, so the four frozensets cannot drift silently.

Harder: nineteen `@mcp.tool()` definitions move at once. The PR is
large in line count but mechanical; the audited-runner wrapping is
the only behaviour that has to stay byte-identical. The
`tests/integration/test_server_lifespan.py` integration test verifies
the surface remains identical to a caller; this is the canonical
contract test for the split.

Alternatives rejected:

- **One big `server.py` plus `# region` comments.** Cosmetic; does
  not let mypy and ruff see per-subsystem boundaries; does not help
  the tier-classifier coverage check.
- **Tools as data (a registry, not decorators).** Would lose the
  FastMCP type-binding magic and force a parallel schema definition;
  the gain is not worth the loss.
- **Group by tier rather than by subsystem.** A T0 read-only tool and
  the T2 stateful write that it shadows belong together for review;
  splitting them by tier puts them in different files.

## Revisit triggers

- The number of registered tools exceeds forty; the per-subsystem
  module size starts to grow past one screen and a finer
  decomposition (per capability rather than per subsystem) may be
  cheaper.
- FastMCP introduces a native tool-registration pattern that
  supersedes the decorator-on-instance approach; the registration
  helper should switch to it.
- A future remote-MCP federation needs to expose only a subset of
  the tool surface; the per-subsystem split makes that selection
  natural, but the `register()` signature may need to grow a filter.
