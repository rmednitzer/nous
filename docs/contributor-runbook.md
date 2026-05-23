# Contributor runbook

A detailed walk-through for a maintainer or AI-assisted contributor who
needs to audit, review, enhance, validate, or extend `nous`. The
[`AGENTS.md`](https://github.com/rmednitzer/nous/blob/main/AGENTS.md) file is the orientation; [`CONTRIBUTING.md`](https://github.com/rmednitzer/nous/blob/main/CONTRIBUTING.md)
is the PR checklist; [`CLAUDE.md`](https://github.com/rmednitzer/nous/blob/main/CLAUDE.md) collects the Claude-specific
addenda. This runbook is the longer-form procedure that ties those three
documents to the live state of the codebase.

The runbook is written so a fresh session can pick it up cold. Every step
names the files it touches, the make target it relies on, and the
governance artefact (ADR, BL-NNN, STPA derived requirement) that the work
needs to keep in sync.

## 0. Pre-flight

Confirm the working environment before touching anything. The toolchain
is `uv` + Python 3.12 or newer (3.14 on the Ubuntu 26.04 baseline per
ADR 0016), with `ruff`, `mypy --strict`, `pytest`, `hypothesis`, and
`mkdocs` installed by `uv sync --all-extras`. The single source of truth
for build commands is the [`Makefile`](https://github.com/rmednitzer/nous/blob/main/Makefile); use the targets
rather than the underlying tools so the next contributor inherits the
same invocation.

```sh
make install                      # uv sync --all-extras
make check                        # ruff + mypy strict + pytest
make docs-build                   # mkdocs build --strict
uv run nous serve                 # stdio MCP server
NOUS_TRANSPORT=http uv run nous serve   # HTTP with OAuth
```

Read [`STATUS.md`](https://github.com/rmednitzer/nous/blob/main/STATUS.md) and [`LIMITATIONS.md`](https://github.com/rmednitzer/nous/blob/main/LIMITATIONS.md)
before anything else. `STATUS.md` lists the current phase (L0 scaffold,
L1 subsystems, L2 claude.ai integration, L3 STPA and benchmarks) and the
maturity of every component. `LIMITATIONS.md` is authoritative on what
is intentionally out of scope. A finding that proposes work already
listed under `LIMITATIONS.md` is not a finding; it is a duplicate.

Set a working branch off `main` named `claude/<short-slug>` or
`feature/<short-slug>` (the patterns in `AGENTS.md`). For an audit run
the branch should not modify code; for a review or enhancement run the
branch should land one logical change at a time so the diff is small
enough for a single PR. The reference instance auto-pulls `main` every
five minutes via `nous-auto-update.timer` (see `docs/deployment.md`), so
treat every merge as immediately live.

## 1. Audit run

An audit produces a point-in-time defects report. The baseline artefact
is [`AUDIT.md`](https://github.com/rmednitzer/nous/blob/main/AUDIT.md), conducted on 2026-05-20 against revision
`a2d0ed4`. A fresh audit either extends `AUDIT.md` in place or lands a
companion `AUDIT-YYYY-MM-DD.md` if the previous report has too many
resolved findings to read clearly. The conducting commit hash and the
date go at the top so the report is reproducible.

Walk the codebase in the order the spine flows. Start with
[`src/nous/policy.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/policy.py),
[`src/nous/runner.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/runner.py),
[`src/nous/audit.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/audit.py),
[`src/nous/server.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/server.py), and
[`src/nous/engine.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/engine.py). These five files carry
the audit invariants: tier classification, audited tool execution,
SHA-256-only output hashing, FastMCP wiring, tick orchestration. A
defect in any of them is automatically Critical or High; document the
class, the file, the line range, the invariant violated, and the
minimal patch. The existing severity legend (Critical, High, Medium,
Low, Strength) in `AUDIT.md` section 2 is the rubric.

Continue through each subsystem under
[`src/nous/subsystems/`](https://github.com/rmednitzer/nous/tree/main/src/nous/subsystems), each estimator under
[`src/nous/estimators/`](https://github.com/rmednitzer/nous/tree/main/src/nous/estimators), each interop adapter
under [`src/nous/interop/`](https://github.com/rmednitzer/nous/tree/main/src/nous/interop), the OAuth issuer in
[`src/nous/auth/`](https://github.com/rmednitzer/nous/tree/main/src/nous/auth), the FSM in
[`src/nous/state/machine.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/state/machine.py), the
Anthropic client in
[`src/nous/anthropic_client.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/anthropic_client.py), the
deploy bundle under [`deploy/`](https://github.com/rmednitzer/nous/tree/main/deploy), and the test tree under
[`tests/`](https://github.com/rmednitzer/nous/tree/main/tests). For each module, capture: contract claimed by the
docstring, behaviour observed in code, gap between the two, and the
smallest reproducer that exposes the gap. Stub modules that return
plausible-looking values without filtering are the most dangerous shape
and warrant a Critical or High; record them under a "stubs that look
real" sub-heading the way `AUDIT.md` C5 records the thermal and compute
estimator stubs.

Finish with cross-cutting concerns: CI workflow under
[`.github/workflows/`](https://github.com/rmednitzer/nous/tree/main/.github/workflows), the policy-grep coverage
that `CLAUDE.md` claims (em-dash ban, private-repo ban), the
documentation-vs-code drift surfaced by `STATUS.md`, and the BOM-to-YAML
provenance chain rooted at [`docs/bom.md`](bom.md). Map every finding
to a BL-NNN id in [`docs/backlog.md`](backlog.md) and to a remediation
sequence at the end of the audit report. The published sequence in
`AUDIT.md` section 9 is the model: order by blast radius and estimated
hours so a maintainer can sprint the list without re-reading the whole
document.

Out-of-scope items go in their own section so the next auditor does not
re-flag them. `AUDIT.md` section 10 lists the patterns that look like
defects but are intentional (FSM raising on unknown trigger, audit
sink swallowing exceptions, scalar Kalman without Joseph form). Mirror
that section in any fresh audit; it is the most effective signal that
the report is calibrated against the project's design choices.

## 2. Review run

A review is lighter than an audit; it focuses on architecture-to-implementation
drift and on the realism of the simulator. The reference artefact is
[`docs/review-2026-05-21.md`](review-2026-05-21.md), which surveys
correctness, security, data, concurrency, error handling, and tests
with prioritised findings and a roadmap. Treat that document as the
template: same six categories, same prioritisation rubric, same closing
"unknowns and minimal checks" list.

The first check is the architecture document against the live engine.
[`docs/architecture.md`](architecture.md) describes a tick that fans
out across every subsystem and refreshes the self-model. The current
[`src/nous/engine.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/engine.py) wires power and APU only.
When the gap widens, either land the wiring or land an explicit
`capability_matrix` / `fidelity_level` field on `device_info` so a
controller can gate behaviour by fidelity. Either way, the review must
either confirm the docs match the code or file a finding.

The second check is the maturity table in [`STATUS.md`](https://github.com/rmednitzer/nous/blob/main/STATUS.md)
against the tool surface in [`src/nous/server.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/server.py)
and the per-document state of every file under `docs/`. A document
flagged `stable` should not be churning week to week; a document
flagged `in-progress` should be moving. If `STATUS.md` claims a
subsystem is `in-progress` but the module is a typed stub returning
constants, downgrade the row or fix the module in the same PR. The
review should never leave `STATUS.md` lying about a component.

The third check is realism. Walk each numeric value in
[`profiles/`](https://github.com/rmednitzer/nous/tree/main/profiles) against [`docs/bom.md`](bom.md). The BOM
is the source of truth; the profile reads from it. A value that has no
BOM row gets one; a BOM row without a citation gets a vendor datasheet,
a MIL-STD reference, or a published benchmark added. The same applies
to estimator covariance bounds: every claim in a model card under
[`docs/model-cards/`](model-cards/README.md) needs to be reproducible against
the estimator code, ideally against a unit test. The review report
captures the gaps and recommends BL-NNN entries.

Close the review with an "unknowns" section. The 2026-05-21 review
listed CI branch protection, real-world calibration error of the
power/APU model, and runtime performance at target tick rates as the
three things that could not be verified from the repository alone.
Pick the same shape: each unknown plus the minimal check that would
resolve it. The next review picks the unknowns up as starting points.

## 3. Enhance run

An enhance run lands a fix or a polish for an existing surface. Pick a
finding from the most recent audit report or a BL-NNN item flagged for
the current phase. The recommended sequencing in `AUDIT.md` section 9
is calibrated for blast radius first, leverage second; follow it unless
the maintainer asks for something specific.

The pattern is the same regardless of the finding. Open the file,
write the failing test under [`tests/unit/`](https://github.com/rmednitzer/nous/tree/main/tests/unit) or
[`tests/integration/`](https://github.com/rmednitzer/nous/tree/main/tests/integration), watch it fail, write
the minimum patch, watch it pass. For a spine file (`policy.py`,
`runner.py`, `audit.py`, `state/machine.py`, `anthropic_client.py`,
`estimators/base.py`, `interop/base.py`, or the hardware-profile
schema) the patch needs an ADR cross-reference in the commit message
even if no new ADR is required, because those files are on the "no
change without an ADR" list in `CLAUDE.md`. If the patch *introduces*
a contract change, an ADR is required: copy
[`docs/adr/0000-template.md`](adr/0000-template.md) to the next number
and fill in Context / Decision / Consequences / Revisit triggers.

For each enhancement that materially changes behaviour, append a line
to [`CHANGELOG.md`](https://github.com/rmednitzer/nous/blob/main/CHANGELOG.md) under `[Unreleased]`. Follow the
Keep a Changelog vocabulary (Added, Changed, Fixed, Removed,
Deprecated, Security). Reference the BL-NNN id and any ADR. The
audit-discovery items from `AUDIT.md` Critical and High classes
should all reference both: the AUDIT line number and the BL-NNN they
landed under, so a future reader can trace a behaviour back to the
report that motivated it.

Three concrete walk-throughs grounded in the current `AUDIT.md`:

```
# C1 anthropic_client.py flush before unlock
# 1. Open src/nous/anthropic_client.py, locate CallCap.increment().
# 2. Move fh.flush() / os.fsync() above fcntl.flock(LOCK_UN).
# 3. Add tests/unit/test_anthropic_client.py exercising concurrent
#    locking with multiprocessing; assert no double-counting.
# 4. Commit: fix(anthropic): flush daily-cap counter before unlock
#            References AUDIT.md C1, ADR-0005.

# C2 recursive redaction in audit.py
# 1. Open src/nous/audit.py, locate redact().
# 2. Replace the flat dict comprehension with a recursive walker
#    that recurses through Mapping and Sequence values.
# 3. Add tests/unit/test_audit.py with a deeply nested payload.
# 4. Commit: fix(audit): recurse argument redaction through nested
#            mappings. References AUDIT.md C2.

# C3 tick task in server lifespan
# 1. Open src/nous/server.py, register a FastMCP lifespan context
#    that schedules nous.tick.tick_loop().
# 2. Cancel the task on shutdown; call engine.stop() so the FSM
#    lands on shutdown rather than leaking the running state.
# 3. Cover with tests/integration/test_server_lifespan.py.
# 4. Commit: fix(server): tick engine through FastMCP lifespan.
#            References AUDIT.md C3, BL-002.
```

Whenever an enhance run touches a high blast radius file, add a
"Security note" paragraph to the PR description per
[`CONTRIBUTING.md`](https://github.com/rmednitzer/nous/blob/main/CONTRIBUTING.md). The Security-note list there
covers `policy.py`, `runner.py`, `audit.py`, `anthropic_client.py`,
`estimators/base.py`, `interop/base.py`, and the hardware-profile
schema (six files plus the schema). The broader ADR-required list in
[`CLAUDE.md`](https://github.com/rmednitzer/nous/blob/main/CLAUDE.md) also
covers `state/machine.py`, but the FSM does not currently require a
Security-note paragraph by itself; track ADR requirements and
Security-note requirements as separate gates. Add the paragraph
proactively whenever the change touches any of the listed surfaces.

## 4. Validate run

Validation is the answer to "does this still do what `STATUS.md` says
it does". The minimum is `make check`, which runs ruff, mypy in strict
mode, and pytest. CI runs the same target; a green CI does not absolve
a contributor from running it locally first. `make docs-build` (which
invokes `mkdocs build --strict`) is the equivalent for the docs tree
and should be green before any PR that touches `.md` files lands.

Beyond the make targets, three layers of validation matter for this
project. The first is the audited tool path: every new tool registered
in `src/nous/server.py` needs at least one test that exercises the
audited call (the runner must produce an audit line), per
`CONTRIBUTING.md`. The second is invariants: energy conservation
across the tick loop, monotonicity of `state.tick` and `state.ts_s`,
SoC clamping in `[0, 1]`, FSM transitions only along the allowed
table. Use `hypothesis` (already a dev dependency) to write a
property-based test for each invariant; the test lives under
[`tests/unit/`](https://github.com/rmednitzer/nous/tree/main/tests/unit) with a `test_invariants_<surface>.py`
name. The third is scenario replayability: each scenario YAML under
[`scenarios/`](https://github.com/rmednitzer/nous/tree/main/scenarios) that lands in the showcase or in CI
needs an integration test under
[`tests/integration/test_scenario_<name>.py`](https://github.com/rmednitzer/nous/tree/main/tests/integration).

Manual smoke is required for any change that touches the server, the
auth issuer, or the deployment bundle. The flow is short:

```sh
# stdio
uv run nous serve
# In another terminal: send a JSON-RPC initialize + tools/list +
# a representative tool call (device_info, state_get).

# HTTP with OAuth (requires NOUS_OAUTH_ENABLED=true)
NOUS_TRANSPORT=http uv run nous serve
curl -s http://127.0.0.1:8088/.well-known/oauth-authorization-server
# Walk the PKCE dance against /authorize, /token, /register per RFC
# 7591/7636. The single-client lockdown means a re-registration
# replaces the previous client; that is intentional.

# scenario
uv run nous scenario scenarios/env-monitoring-urban.yaml
tail -f "${NOUS_AUDIT_PATH:-$NOUS_HOME/audit.jsonl}"   # confirm audit lines arrive
```

For UI-shaped changes (the showcase site), build the site locally
(`make docs-build` then `mkdocs serve`) and click through the fidelity
page, the FSM viewer, and the capability matrix. The showcase is the
public face of the project (ADR 0017); a broken link or stale capability
column is a regression even if every test passes.

Capture the validation evidence in the PR description's "Blast radius"
and "Rollback path" sections. The conventional content is: which
components were exercised, which tests were added or extended, which
manual checks were run, and what `git revert` would have to undo. The
PR descriptions in the `claude/repo-audit-best-practices-fHVFy` and
subsequent branches are worked examples.

## 5. Extend run

An extend run adds new functionality. The canonical recipes live in
[`AGENTS.md`](https://github.com/rmednitzer/nous/blob/main/AGENTS.md) under "Canonical recipes"; this section
expands each recipe with the order of operations, the files that need
attention, and the cross-references that keep the docs honest.

### 5.1 Adding a subsystem

Pick the simplest physics model that matches reality: a one-state
Kalman beats a multi-state EKF if both meet the covariance bound in
the model card. Drop the module under
[`src/nous/subsystems/<name>.py`](https://github.com/rmednitzer/nous/tree/main/src/nous/subsystems) implementing
the `Subsystem` Protocol (`step / truth / sensor_obs`). Add the curves
to [`profiles/jetson-agx-orin.yaml`](https://github.com/rmednitzer/nous/blob/main/profiles/jetson-agx-orin.yaml)
with citations propagated from [`docs/bom.md`](bom.md); update the
other profiles or document why they differ. Add an estimator under
[`src/nous/estimators/<name>.py`](https://github.com/rmednitzer/nous/tree/main/src/nous/estimators); pair it
with a model card under
[`docs/model-cards/estimator-<name>-<filter>.md`](model-cards/README.md) that
documents the covariance bound.

Wire the subsystem into [`src/nous/engine.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/engine.py)
(both `Engine.__init__` and the tick step), and register an MCP tool
that reads the estimated state. Classify the tool T0 in
[`src/nous/policy.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/policy.py); only mutating tools earn
T1 or higher per ADR 0013. Add at least one unit test under
[`tests/unit/test_subsystem_<name>.py`](https://github.com/rmednitzer/nous/tree/main/tests/unit) and one
integration test that ticks the engine and asserts the estimator
converges to truth within the bound. Update
[`STATUS.md`](https://github.com/rmednitzer/nous/blob/main/STATUS.md) to flip the row from `planned` to
`in-progress`, and append a `Added` entry to
[`CHANGELOG.md`](https://github.com/rmednitzer/nous/blob/main/CHANGELOG.md) referencing the BL-NNN.

If the subsystem changes a contract (new sensor format, new vocabulary,
new field on the profile schema), open an ADR. The thermo-optical
subsystem in BL-055 is the worked example currently on the backlog.

### 5.2 Adding an MCP tool

Decide the tier first. The default is T0 read-only; a tool that mutates
engine or scenario state is T2; a tool that triggers an external
side-effect (publish, broadcast, write to disk outside `$NOUS_HOME`) is
T3. T1 is reserved for reversible mutations (e.g. set-then-undo). The
classification goes in [`src/nous/policy.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/policy.py) at
registration; conservative defaults err high.

Register the tool in [`src/nous/server.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/server.py).
The handler must call `app.run(tool=..., ctx=..., audit_args=...,
policy_text=..., work=...)` so the runner records an audit line. The
handler should never write to disk directly and should never call
the Anthropic client without going through
[`src/nous/anthropic_client.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/anthropic_client.py).

Update [`docs/tool-reference.md`](tool-reference.md) (or run
`make schema` to regenerate it). Add at least one test under
[`tests/unit/test_server.py`](https://github.com/rmednitzer/nous/tree/main/tests/unit) or
[`tests/integration/`](https://github.com/rmednitzer/nous/tree/main/tests/integration) that exercises the
audited path. The audit line is the contract; assert on it.

### 5.3 Adding a scenario

Drop a YAML file under [`scenarios/<name>.yaml`](https://github.com/rmednitzer/nous/tree/main/scenarios) with
the top-level keys the `Scenario` loader expects: `schema_version`,
`meta` (name, description, tags), `profile` (the hardware profile id),
`tick_budget` (the maximum number of ticks before the scenario ends),
and `steps` (a timeline of `{at_min, action, args}` entries; injection
actions like `inject_sensor_drift` live inside `steps`, not at the top
level). Reference the profile the scenario expects; if the scenario
relies on a non-reference profile, add a sentence to
[`docs/scenarios/README.md`](scenarios/README.md) explaining why.

If the scenario is meant to be replayable in CI, add a test under
[`tests/integration/test_scenario_<name>.py`](https://github.com/rmednitzer/nous/tree/main/tests/integration)
that loads, runs, and asserts the closing engine state. Showcase
scenarios get a page under
[`docs/showcase/scenarios/`](showcase/scenarios/README.md) generated by
`scripts/gen_showcase_telemetry.py`; rerun the script if you change
the scenario's tick count or end state.

### 5.4 Adding a hardware profile

Copy [`profiles/jetson-agx-orin.yaml`](https://github.com/rmednitzer/nous/blob/main/profiles/jetson-agx-orin.yaml)
and edit the curves. The citation header at the top of the YAML is
mandatory; every numeric value needs to trace to a row in
[`docs/bom.md`](bom.md). Run `make schema` to regenerate the JSON
Schemas the project does emit (`AuditRecord`, `Scenario`) under
[`docs/schema/`](https://github.com/rmednitzer/nous/tree/main/docs/schema);
note that `Engine._load_profile()` today calls `yaml.safe_load`
without schema validation, so a typo in a profile key degrades
silently to the default (AUDIT M10, BL-006). Until BL-006 lands, the
load-time validation step is a manual diff against
[`profiles/jetson-agx-orin.yaml`](https://github.com/rmednitzer/nous/blob/main/profiles/jetson-agx-orin.yaml).
Add a section to [`docs/hardware-profiles.md`](hardware-profiles.md)
and a one-line entry in the profiles README, then update
[`STATUS.md`](https://github.com/rmednitzer/nous/blob/main/STATUS.md) if the new profile shifts the maturity of
the schema row.

### 5.5 Adding an interop adapter

Implement the `Adapter` Protocol in
[`src/nous/interop/base.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/interop/base.py). The
encode/decode pair must be well-formed even at stub maturity; the
audit explicitly flagged stubs that emit malformed output (MISB key
truncation, CoT missing required attributes, incomplete NMEA GGA) as
High findings precisely because a controller can be misled.

Add a conformance document under
[`docs/conformance/<standard>.md`](https://github.com/rmednitzer/nous/tree/main/docs/conformance) declaring the QoS
policy, the supported envelope, the deliberate omissions, and the
gap between the v0.1 posture and the standard. Cite the canonical
source per the `CLAUDE.md` citations convention; do not paste excerpts
into the document.

### 5.6 Adding an ADR

Copy [`docs/adr/0000-template.md`](adr/0000-template.md) to the next
number. Fill in Status, Date, Authors, Context, Decision,
Consequences, Revisit triggers. Keep it to one page; the existing
ADRs (0001 through 0018) are the bar. Update
[`docs/adr/README.md`](adr/README.md), or regenerate it with
`scripts/gen_adr_index.py`. ADRs cited from STPA derived requirements
need a back-reference: open
[`docs/stpa/09-derived-requirements.md`](stpa/09-derived-requirements.md)
and add the ADR id to the relevant row.

### 5.7 Adding a backlog item

Append to [`docs/backlog.md`](backlog.md) with the next `BL-NNN` id, a
one-line summary, the phase (L0..L3), a `[planned]` status. Move to
`[in-progress]` and `[done]` as work lands. If the item resolves a
finding in `AUDIT.md` or in a review document, cite the finding number
inline. If the item is referenced from an STPA derived requirement,
prefix the description with the DR-N id.

## 6. Backlog work

The backlog in [`docs/backlog.md`](backlog.md) sequences work by
phase. L0 is scaffold (the `[in-progress]` BL-001 covers the v0.1 PR
itself). L1 is subsystem models and the state machine wiring. L2 is
claude.ai integration and the scenario pack. L3 is STPA completion,
real local inference, propagation-aware comms, and the additional
adapters. Items inherit the additive-surface rule (ADR-0007) once L0
ships; a change that breaks an existing tool signature needs an ADR
even if the BL row exists.

Pick items by phase first, then by dependency, then by blast radius.
A practical sprint for the current state of the repo is:

```
# Sprint 1 (close audit Criticals + spine tests)
BL-021 + AUDIT C1   # anthropic flush-before-unlock + structured CapExhausted
BL-016 + AUDIT C6   # audit hash chain plus CI policy greps
BL-035 + AUDIT C5   # self-model sentinels and calibrated quantiles
# Sprint 2 (close audit Highs that depend on spine work)
BL-024 + AUDIT H3   # CoT adapter completes the required attributes
BL-025 + AUDIT H4   # SensorThings adapter normalises to UTC
BL-033 + AUDIT H5   # NMEA emits the full GGA sentence
# Sprint 3 (subsystem wiring for L1 readiness)
BL-005 / BL-007 / BL-005b   # thermal, compute, PMU/PDU
BL-018                       # self-model assess + viability wiring
```

A finding without a BL-NNN should get one before the work starts; a
BL-NNN without a finding it resolves should cite an ADR or STPA derived
requirement instead. The link between the work tracker and the
governance artefacts is the trace that keeps the project legible.

Status semantics are strict. `[planned]` means scoped but unstarted.
`[in-progress]` means there is a branch, a stub, or a partial PR.
`[done]` means it has landed on `main` and `STATUS.md` reflects it.
Move the marker in the same commit that lands the work, not after.

## 7. Cleanups, consolidations, and refactoring

Refactoring inside the low-blast-radius surfaces is free to iterate.
Tool wiring in [`src/nous/server.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/server.py) (provided
the tier is set correctly), subsystem physics curves in profile YAML,
scenario YAML files, and docs (README, ADR additions, model cards,
conformance posture) are all on the low list per `CLAUDE.md`. Land
the smallest possible diff per PR; the maintainer can compose larger
sequences from the merge log.

High blast radius surfaces require an ADR before any change.
[`src/nous/policy.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/policy.py),
[`src/nous/runner.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/runner.py),
[`src/nous/audit.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/audit.py),
[`src/nous/state/machine.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/state/machine.py),
[`src/nous/anthropic_client.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/anthropic_client.py),
[`src/nous/estimators/base.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/estimators/base.py),
[`src/nous/interop/base.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/interop/base.py), and the
hardware-profile schema in [`profiles/`](https://github.com/rmednitzer/nous/tree/main/profiles) are the seven
files plus one schema on the ADR-required list. The Security-note
requirement in
[`CONTRIBUTING.md`](https://github.com/rmednitzer/nous/blob/main/CONTRIBUTING.md)
covers a narrower set (six of those files plus the schema; the FSM in
`state/machine.py` is ADR-gated but not on the Security-note list).
Treat the two requirements as separate gates: ADRs document the
decision, Security notes document the threat-model implications.

The known consolidation candidates as of the 2026-05-23 working state:

The first is the estimator base. Each estimator currently implements
its own `predict / update / state` triple. As more filters land
(thermal, compute, biometrics, comms), the boilerplate around
covariance bookkeeping and step accounting will repeat; consolidating
into a `BaseEstimator` mixin under
[`src/nous/estimators/base.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/estimators/base.py) is
defensible only if the resulting class still leaves the filter
implementation under twenty lines (the bar `PowerEstimator` set). If
the mixin grows beyond that, leave the implementations independent.

The second is the interop encoder. The CoT, SensorThings, MISB KLV,
and NMEA encoders all build a structured record from `data`, validate
it, and serialise. The validation and the
"required-attributes-by-standard" tables could move into
[`src/nous/interop/base.py`](https://github.com/rmednitzer/nous/blob/main/src/nous/interop/base.py) as a
declarative schema, but only after each adapter ships a complete
encoder (the audit High findings H3, H4, H5 must land first). A
consolidation against incomplete encoders entrenches the gaps.

The third is the subsystem stub posture. Several v0.1 subsystems
return constants from `truth()` and `sensor_obs()`. The audit's C5
finding recommends a `_stub: True` sentinel in the covariance dict so
a controller can distinguish "I have no estimate" from "I have a
zero-error estimate". The same pattern applies to
[`src/nous/self_model/`](https://github.com/rmednitzer/nous/tree/main/src/nous/self_model) where p5 / p50 / p95
are all `0.0`. Land the sentinel pattern in one PR across every stub
before any per-subsystem implementation work; it is the smallest
consolidation that prevents the most expensive class of bug (a
controller acting on a plausible zero).

The fourth is the deployment bundle. `deploy/install.sh`,
`deploy/auto-update.sh`, the systemd units under
[`deploy/systemd/`](https://github.com/rmednitzer/nous/tree/main/deploy/systemd), and the Caddyfile template
all carry repeated path constants (`$NOUS_HOME`, `/var/log/nous`,
`/opt/nous`). A `deploy/paths.env` file sourced by every script and
templated into every unit would remove the drift risk, and would land
cleanly behind the systemd `EnvironmentFile=` directive. This is a
docs-and-shell change, no Python, but warrants an ADR if the path
contract changes.

The fifth is the doc tree itself. The next section walks the full
markdown update procedure.

## 8. Markdown update run

A markdown sweep is a discrete contribution shape: no Python changes,
no behaviour changes, only documentation freshness. The reference
artefact is the PR sequence that landed
[`docs/review-2026-05-21.md`](review-2026-05-21.md) and the
`docs: bring markdown tree up to date with current code and ADR 0017`
commit (e0b3c7b). Follow the same shape.

### 8.1 Establish the baseline

Inventory every markdown file in the tree. The `find` invocation is
the canonical one (excluding caches and the git directory):

```sh
find . -name "*.md" \
    -not -path "./node_modules/*" \
    -not -path "./.git/*" \
    -not -path "./.venv/*" \
    -not -path "./site/*" \
    | sort > /tmp/nous-md-inventory.txt
wc -l /tmp/nous-md-inventory.txt
```

Read the inventory once end-to-end before editing anything. The tree
currently spans the top level (README, AGENTS, CLAUDE, CONTRIBUTING,
SECURITY, STATUS, LIMITATIONS, CHANGELOG, AUDIT), the
[`docs/`](README.md) tree (architecture, backlog, deployment, releasing,
bom, hardware-profiles, state-machine, tool-reference, the review
artefact, this runbook), [`docs/adr/`](adr/README.md) (the numbered ADRs and
the index), [`docs/stpa/`](stpa/README.md) (the numbered STPA artefacts),
[`docs/conformance/`](https://github.com/rmednitzer/nous/tree/main/docs/conformance) (per-standard posture),
[`docs/model-cards/`](model-cards/README.md) (per-subsystem and per-estimator),
[`docs/showcase/`](showcase/README.md) (the public-facing site),
[`docs/subsystems/`](subsystems/README.md),
[`docs/scenarios/`](scenarios/README.md), the
[`skills/`](https://github.com/rmednitzer/nous/tree/main/skills) runbooks, the
[`deploy/README.md`](https://github.com/rmednitzer/nous/blob/main/deploy/README.md), and the
[`examples/inspector_quickstart.md`](https://github.com/rmednitzer/nous/blob/main/examples/inspector_quickstart.md).

### 8.2 Check the cross-references

Every markdown link should resolve. Two greps catch most of the rot:

```sh
# Internal markdown links that point at files
grep -rEn '\]\((\.\.?/|docs/|src/|tests/|deploy/|profiles/|scenarios/|skills/|examples/)[^)]+\.md\)' \
    --include='*.md' .

# BL-NNN references
grep -rEn '\bBL-[0-9]{3}[a-z]?\b' --include='*.md' .

# ADR references
grep -rEn '\bADR[ -]?[0-9]{4}\b' --include='*.md' . 
```

For each hit, confirm the target exists and the heading anchor (if
any) is still valid. The MkDocs `strict` mode catches broken links
at site-build time (`make docs-build`), but the BL-NNN and ADR
references go beyond what MkDocs can validate. A BL-NNN reference must
resolve to a row in [`docs/backlog.md`](backlog.md); an ADR reference
must resolve to a file under [`docs/adr/`](adr/README.md).

### 8.3 Enforce the em-dash ban

`CLAUDE.md` declares the em-dash ban; the CI grep is the enforcement
mechanism (or should be, per audit C6). Run the grep manually until
the CI step lands:

```sh
! grep -rPn '\x{2014}' --include='*.md' .   # U+2014 EM DASH
! grep -rPn '\x{2013}' --include='*.md' .   # U+2013 EN DASH (optional)
```

Replace any hit with `--`, a comma, a colon, or a parenthetical, per
the convention. The ban is repository-wide for markdown (including
fenced code blocks); only source-code strings under `src/` may
contain U+2014 if the string genuinely needs one.

### 8.4 Cross-check maturity claims

Every component status in [`STATUS.md`](https://github.com/rmednitzer/nous/blob/main/STATUS.md) needs a
matching reality. Walk the component table and confirm the maturity
flag for each module against the actual code: `stable` modules should
have an ADR governing changes and a test suite covering the contract,
`in-progress` should have at least one wired-up call path, `planned`
should be a typed stub. If a row drifts, fix the row in this PR.

Same procedure for the per-document state table: `stable` ADRs should
not be edited (a new ADR supersedes them), `in-progress` documents
should be moving (a commit in the last sprint), `planned` should
either become a stub file or come out of the table.

### 8.5 Refresh the BOM and the model cards

[`docs/bom.md`](bom.md) is the realism anchor for every numeric value
in [`profiles/`](https://github.com/rmednitzer/nous/tree/main/profiles). For each row, confirm the citation is
still the best public reference and the numeric value still matches
the profile YAML. If a profile drifted from the BOM, fix the profile
or the BOM in the same PR; never let the two diverge.

Each estimator and subsystem model card under
[`docs/model-cards/`](model-cards/README.md) needs the same check against the
estimator code. The covariance bound, the warm-up period, the
divergence conditions, and the "do not use for X" caveats should all
match the implementation. The audit's C5 finding is the cautionary
example: a model card that claims a calibrated covariance but is
backed by a stub returning constants is worse than a model card that
declares the subsystem unimplemented.

### 8.6 Sweep the showcase and the public face

[`docs/showcase/`](showcase/README.md) is the externally visible artefact; ADR
0017 documents the lockdown posture and the rationale for keeping the
production VM CIDR-gated. The capability matrix, the fidelity badges,
and the FSM viewer should reflect the live `main` state. If
`scripts/gen_showcase_telemetry.py` produced telemetry against a
different scenario or profile than the showcase claims, regenerate or
fix the claim.

The top-level [`README.md`](https://github.com/rmednitzer/nous/blob/main/README.md), [`STATUS.md`](https://github.com/rmednitzer/nous/blob/main/STATUS.md),
and [`LIMITATIONS.md`](https://github.com/rmednitzer/nous/blob/main/LIMITATIONS.md) are the next-most-visible
files. The "Last reviewed" date in `STATUS.md` and `LIMITATIONS.md`
should be updated to the date of the sweep. Capability lists and
limitation rows that no longer match `main` get rewritten; a new
limitation that emerged since the last sweep gets a fresh `LN`
identifier.

### 8.7 Update the changelog

If the sweep is substantive (more than typo fixes), append a
`Changed` or `Fixed` entry to the `[Unreleased]` block in
[`CHANGELOG.md`](https://github.com/rmednitzer/nous/blob/main/CHANGELOG.md). The convention is one bullet per
material clarification, with a parenthetical pointing at the affected
files. Pure typo fixes do not warrant a CHANGELOG entry.

### 8.8 Regenerate and validate

Regenerate the generated docs and rebuild the site:

```sh
make schema        # tool-reference.md, ADR index, backlog summary, JSON schemas
make docs-build    # mkdocs build --strict
```

`mkdocs build --strict` will fail on a broken link, a missing
navigation entry, an orphan page, or a Markdown extension parse
error. Resolve each warning rather than silencing it.

### 8.9 Land as one PR

A markdown sweep ships as a single PR titled
`docs: bring markdown tree up to date with current code and ADR
NNNN` (or similar). The PR body lists the files touched in three
groups (top-level, `docs/`, `skills/`), references the audit or
review that motivated the sweep, and notes any cross-cutting findings
(em-dash bans triggered, BL-NNN references repaired, STATUS.md rows
that changed maturity). The maintainer's review focuses on whether
the maturity claims still match `main`; the cosmetic changes are
secondary.

A sweep that is too large to review as one PR is a signal to split by
sub-tree: `docs: refresh STPA artefacts`, `docs: refresh model
cards`, `docs: refresh conformance posture` are the natural splits.
Each split carries its own CHANGELOG entry if substantive.

## 9. Closing the loop

Every contribution flows back to four places. `STATUS.md` reflects
the new maturity of every component the change touched. `CHANGELOG.md`
captures the user-visible behaviour. The backlog
[`docs/backlog.md`](backlog.md) advances the relevant `BL-NNN` rows.
The audit artefact ([`AUDIT.md`](https://github.com/rmednitzer/nous/blob/main/AUDIT.md) or its successor) crosses
off the finding(s) the change resolved. A PR that leaves any of those
four out of sync is incomplete.

The reference rhythm is: audit on a fixed cadence (quarterly, or after
a phase boundary), review on a lighter cadence (monthly), enhance and
validate continuously, extend per the BL-NNN sprint, sweep markdown
every time the maturity table shifts. Following the rhythm keeps the
governance documents honest and the simulator legible to the next
controller that picks up the surface.
