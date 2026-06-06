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
pre-1.0 and runs entirely in software. The L1 subsystem rollout is on
`main` (ten subsystems, nine estimators), the self-model layer emits
calibrated capability claims (BL-018, BL-035), and the scenario loader
and injectors drive the engine end to end (BL-014). What it is not: no
number has been compared against measured traces from real hardware, and
the interop conformance is self-declared, not certified. See the
[2026-06-06 audit](../audit-2026-06-06.md) and `AUDIT.md` for the
substance findings. The fidelity badges exist to keep the showcase
honest about that. ADR 0017 records the decision behind this section.

If you are looking for the live reference instance, it remains
private and gated; see `docs/deployment.md` for the deployment
pattern. The live VM tracks `origin/main` via auto-update; if `main`
lags the development line, the live MCP serves an older surface than
this showcase claims (see audit-2026-06-06 §6 for the most recent
probe).
