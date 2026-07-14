# Showcase

This section is the public, fixture-driven view of `nous`. Every page in
the showcase carries a fidelity badge so a reader can tell at a glance
whether a number came out of a calibrated filter, a real subsystem with
no filter on top, a stub returning a constant, or a planned surface that
has not landed yet. The legend lives in [Fidelity](fidelity.md).

The four pages below are the heart of the showcase. The
[scenario gallery](scenarios/README.md) is regenerated on every docs
build by `scripts/gen_showcase_telemetry.py`; the rest are hand
authored and reviewed when the code they describe changes.

| Page | What it shows | How it stays current |
| --- | --- | --- |
| [Fidelity](fidelity.md) | The badge enum and per-subsystem mapping. | Reviewed when a subsystem's substance level changes. |
| [State machine](state-machine.md) | Mission posture FSM with every transition. | Reviewed when `src/nous/state/machine.py` changes. |
| [Capability matrix](capability-matrix.md) | Per-subsystem implementation, estimator, and model card. | Reviewed alongside the backlog. |
| [Scenario gallery](scenarios/README.md) | Per-scenario telemetry, sparklines, timelines. | Regenerated in CI from scenario YAML. |

The showcase is deliberately not a marketing page. The simulator is
pre-1.0 and runs entirely in software. The subsystem rollout is on
`main` (twelve subsystems, ten estimators, including the BL-005b PMU
power management and the BL-055 EO/IR perception payload), the self-model
layer emits calibrated capability claims (BL-018, BL-035), the comms stack
carries a store-and-forward outbox, a multi-node DTN mesh, and operator
EMCON posture (BL-077, BL-056, BL-060), and the scenario loader and
injectors drive the engine end to end (BL-014). What it is not: no number has been
compared against measured traces from real hardware, and the interop
conformance is self-declared, not certified. See the
[2026-06-15b audit](../audit-2026-06-15b.md) and `AUDIT.md` for the
substance findings. The fidelity badges exist to keep the showcase
honest about that. ADR 0017 records the decision behind this section.

There is no public live instance; this showcase is generated from
scenarios at docs-build time and stands on its own. See
`docs/deployment.md` for the reference deployment pattern: a host stood
up from the bundle tracks `origin/main` via auto-update, so if `main`
lags the development line its MCP surface can trail what this showcase
claims (the 2026-06-14b audit records the last probe taken against a
running instance).
