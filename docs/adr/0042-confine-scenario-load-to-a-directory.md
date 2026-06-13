# ADR 0042: Confine scenario_load to a configured scenarios directory

- **Status:** Proposed
- **Date:** 2026-06-13
- **Authors:** rmednitzer
- **Builds on:** ADR 0007, ADR 0013

## Context

The `scenario_load` tool (T2) takes a caller-supplied `path` and hands it to
`load_scenario_file`, which does `Path(path).expanduser()` with no `.resolve()`
and no confinement (`src/nous/scenarios/loader.py:85`). An authenticated T2
caller can therefore point the loader at any readable file on the host. The
2026-06-13 audit logged this as finding S-03 (CWE-22, path traversal).

Practical impact today is bounded: reads are gated behind T2 admission, and a
non-scenario file usually validates into an empty or default `Scenario` whose
contents are never echoed back to the caller. Two residual concerns remain. The
caller-supplied path is recorded verbatim in the audit trail, and a crafted
YAML (large `tick_budget` over many steps) is a resource-exhaustion vector in
the runner.

The reason this is a decision and not a silent fix is that the CLI workflow
`nous scenario <path>` (documented in the README quickstart) deliberately
accepts arbitrary paths, including absolute ones. Clamping the loader
unconditionally would break that path, so the seam where confinement applies
(the MCP tool, not the library function) and the configured root both need a
deliberate choice.

## Decision

Proposed: introduce `NOUS_SCENARIOS_DIR` (default `./scenarios`) and confine
the `scenario_load` *tool* to it. The tool resolves the requested path against
the configured root, calls `.resolve()`, and refuses any target that escapes
the root with a structured `{ok: false, reason: "outside scenarios dir"}`. The
library `load_scenario_file` keeps accepting arbitrary paths so the CLI
(operator-trusted, not network-reachable) is unaffected; the confinement lives
at the network-facing tool boundary, consistent with the tier model (ADR 0013).

## Consequences

A network controller can no longer use `scenario_load` to probe the host
filesystem, and the audit trail stops carrying attacker-chosen absolute paths.
The cost is one more configuration knob and a behavior difference between the
CLI and the tool that must be documented in the tool reference and the
scenario-walkthrough runbook. The runner-side resource-exhaustion vector is
mitigated separately by the existing tick-budget bound, not by this ADR.

Rejected alternative: clamping `load_scenario_file` itself. It would break the
documented CLI workflow and conflate the operator-trusted and network-facing
surfaces.

## Revisit triggers

Revisit if scenarios need to load from multiple roots (a packaged set plus an
operator set), if remote scenario fetch is ever added, or if the CLI and tool
paths are unified behind one loader.
