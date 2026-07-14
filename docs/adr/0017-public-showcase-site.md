# ADR 0017: Public showcase site on the existing docs Pages target

- **Status:** Accepted
- **Date:** 2026-05-21
- **Authors:** rmednitzer
- **Builds on:** ADR 0014 (Docs site on MkDocs with GitHub Pages)

## Context

The project today has two public-facing surfaces. The first is the docs
site at `rmednitzer.github.io/nous` (ADR 0014), which is internally
oriented: ADRs, STPA artefacts, conformance posture, model cards. The
second is a live MCP endpoint behind Caddy and CIDR gating, referenced by
FQDN in `README.md`, `STATUS.md`, and ADR 0016. Neither surface helps a
first-time reader form a quick, honest picture of what the simulator
does and how mature each subsystem is.

The pre-1.0 maturity profile makes a "look how cool this is" demo
actively dangerous. Most subsystems are stubs that return plausible
constants; five of seven estimators do not yet implement the math their
names advertise (per the 2026-05-20 in-house audit). A showcase that
plots `self_model_assess` output without disclosing fidelity would be
the exact failure mode the simulator is designed to prevent: a viewer
forming confidence in numbers that have no calibration behind them.

A third pressure was the past public exposure of the live deployment
FQDN in the repo. The auto-update timer makes that FQDN an attractive
target; the surface is gated but the gate depends on hardcoded Anthropic
egress ranges. A public showcase that satisfies the "transparency about
what nous does" goal removes the operational need to advertise a live
deployment.

## Decision

The showcase is a new section under the existing MkDocs site at
`docs/showcase/`. It carries four pages: an overview, a fidelity badge
reference, a state-machine viewer, and a per-subsystem capability
matrix. A fifth page is a scenario gallery whose contents are
regenerated each docs build by `scripts/gen_showcase_telemetry.py`.

Every chart, table, and metric on every showcase page carries a
fidelity badge drawn from a fixed enum: `validated`, `filtered`,
`parametric`, `stub`, or `planned`. The enum is defined once in
`docs/showcase/fidelity.md` and referenced by every other showcase
page. Stub subsystems render their estimator covariance as `null` on
the showcase rather than as a numeric zero so a reader cannot mistake
absence-of-filtering for high-confidence output.

The telemetry generator drives each `scenarios/*.yaml` through the
engine using the existing `engine.tick()` loop and the scenario step
actions that the engine can honour today (`state_transition`,
`inject_apu` setters). Steps the engine cannot yet apply
(BL-014 injectors) are recorded as `skipped` annotations in the
output. JSONL telemetry per scenario lands under
`docs/showcase/data/`; the per-scenario summary markdown lands under
`docs/showcase/scenarios/`. Both directories are committed so the
site is browseable on GitHub without running the generator. CI
regenerates them in `.github/workflows/docs.yml` before the strict
MkDocs build.

The live deployment FQDN is removed from `README.md`, `STATUS.md`, and
ADR 0016 as a follow-up to this ADR. The showcase becomes the public
face; the live VM remains private and CIDR-gated.

## Consequences

Easier: a first-time reader can see what each scenario produces and
which subsystems contributed real physics versus default values.
Maturity claims become testable in the most basic sense (the build
fails if the generator cannot produce telemetry from a scenario).
Retiring the FQDN from the repo closes an attack-surface advertisement
without losing transparency.

Harder: every change that adds or removes a subsystem's substantive
behaviour must update the capability matrix and, where appropriate,
the fidelity badge on the matching showcase page. The generator and
the docs build now share a coupling: a regression that breaks the
generator breaks the docs CI.

Explicitly rejected: a separate site (Vercel, Netlify, dedicated
domain) was considered and rejected because it doubles the deployment
surface and adds a second auth model. A dynamic site backed by the
live MCP server was rejected because it would re-expose the gated
endpoint to public traffic. A blanket "demo" page without fidelity
badges was rejected because it directly contradicts the legibility
contract in `CLAUDE.md`.

## Revisit triggers

- A subsystem becomes complete enough that the fidelity badge system
  no longer adds signal (every badge is `filtered` or `validated`).
- The scenario gallery grows past a size that comfortably fits inside
  the strict MkDocs build budget (current docs CI timeout is 15 min).
- A regulated downstream consumer requests a signed showcase artefact
  (PDF or hash-chained JSONL) rather than a Pages site.
- The Pages deploy target migrates off `github.io` and the showcase
  needs to follow.
