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
v0.1; eight of ten subsystems are stubs and five of seven estimators
do not yet implement the math their names advertise (see the
[2026-05-21 review](../review-2026-05-21.md) and `AUDIT.md`). The
fidelity badges exist to keep the showcase honest about that. ADR 0017
records the decision behind this section.

If you are looking for the live reference instance, it remains
private and gated; see `docs/deployment.md` for the deployment pattern.
