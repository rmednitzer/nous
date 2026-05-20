# AGENTS.md

Orientation for any AI-assisted contributor working in this repository. This
file follows the cross-vendor `agents.md` convention and is compatible with
Claude, Codex, and Cursor agents.

## What `nous` is

A simulator for a man-portable AI inference appliance: tick-loop physics,
subsystem state estimators, a self-model capability layer, and an MCP tool
surface that a controller (typically a Claude session) drives. The runtime
is asyncio, the build is `uv` + hatchling, the configuration is
`pydantic-settings`, and the tool surface is FastMCP.

## Stack

- Python 3.12, `uv` for dependency management, `hatchling` for build
- `mcp>=1.27` (FastMCP), `pydantic>=2.11`, `pydantic-settings`, `sqlmodel`,
  `alembic`, `anthropic`, `numpy`, `filterpy`, `pynmea2`, `paho-mqtt`,
  `pyyaml`, `httpx`, `anyio>=4.6`, `uvicorn`, `starlette`
- Dev: `pytest`, `pytest-asyncio` (asyncio_mode auto), `ruff`, `mypy`
  (strict), `hypothesis`, `mkdocs`, `mkdocs-material`, `mkdocstrings[python]`

## Where to start

- [README.md](README.md) -- the public face of the project
- [STATUS.md](STATUS.md) -- where each subsystem sits today
- [LIMITATIONS.md](LIMITATIONS.md) -- explicit scope boundaries
- [docs/architecture.md](docs/architecture.md) -- how the pieces fit together
- [docs/backlog.md](docs/backlog.md) -- BL-NNN tracker (work is referenced by id)
- [docs/adr/](docs/adr/) -- decision records, numbered, kept short
- [src/nous/server.py](src/nous/server.py) -- tool surface and audited runner
- [src/nous/engine.py](src/nous/engine.py) -- tick loop orchestration

## Conventions

### Code

- Ruff for lint + format; mypy in strict mode; targets must pass before push.
- Every public function carries a type signature.
- Every Python module opens with a one-line docstring describing its role.
- No em-dashes in prose anywhere in the repository. Use `--` if you need to
  approximate one in markdown. Source code may use them inside strings.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`) with `git commit
  -s` for the DCO sign-off line.

### Tools

- Every MCP tool is tier-classified (T0 read-only / T1 reversible / T2
  stateful / T3 irreversible) by `src/nous/policy.py`. New tools must be
  classified at registration; conservative defaults err high.
- Every tool call runs through `src/nous/runner.py`. The runner records
  one audit line per call. Output bodies are hashed (SHA-256), never logged.
- Argument redaction strips `Authorization`, tokens, passwords, and any key
  matching the redaction allowlist before the audit record is written.

### Configuration

- All knobs live in `pydantic-settings` with the `NOUS_` prefix. Invalid
  values fail fast at startup.
- Hardware curves and limits live in `profiles/*.yaml`. The YAML is the
  source of truth; code reads it, never the other way round.

### Documentation

- ADRs go in `docs/adr/NNNN-<slug>.md`, numbered, with Status / Date /
  Authors / Context / Decision / Consequences / Revisit triggers.
- The backlog (`docs/backlog.md`) tracks line items as `BL-NNN`. Reference
  the id in commit messages and PR titles where possible.
- The STPA artefacts (`docs/stpa/`) follow the numbered file layout
  (01-purpose through 09-derived-requirements).

## Canonical recipes

### Adding a subsystem

1. Add a parametric model under `src/nous/subsystems/<name>.py` implementing
   the `Subsystem` Protocol (`step / truth / sensor_obs`).
2. Add curves to `profiles/jetson-agx-orin.yaml`. Update other profiles or
   document why they differ.
3. Add an estimator under `src/nous/estimators/<name>.py`. Pick the simplest
   filter that meets the model card's covariance bound.
4. Wire the subsystem into `src/nous/engine.py` (`Engine.__init__` and the
   tick step).
5. Add an MCP tool that reads the estimated state. Classify it T0.
6. Add at least one unit test and a model card under `docs/model-cards/`.
7. Open an ADR if the subsystem changes a contract (e.g. introduces a new
   sensor format).

### Adding an MCP tool

1. Decide the tier (default T0 unless the tool mutates state).
2. Register it in `src/nous/server.py`. The handler must call
   `app.run(tool=..., ctx=..., audit_args=..., policy_text=..., work=...)`.
3. Update `docs/tool-reference.md` (or regenerate it with `make schema`).

### Adding a scenario

1. Drop a YAML file under `scenarios/<name>.yaml` with `meta`, `injectors`,
   and a `steps` timeline.
2. Reference the profile it expects.
3. Add an integration test under `tests/integration/test_scenario_<name>.py`
   if the scenario is meant to be replayable in CI.

### Adding a hardware profile

1. Copy `profiles/jetson-agx-orin.yaml` and edit the curves.
2. Validate the schema with `make schema` (regenerates JSON Schemas).
3. Add a section to `docs/hardware-profiles.md` and a one-line entry in the
   profiles README.

### Adding an ADR

Copy `docs/adr/0000-template.md` to the next number and fill it in. Keep it
to one page. Update `docs/adr/README.md` (or regenerate it with
`scripts/gen_adr_index.py`).

### Adding a backlog item

Append to `docs/backlog.md` with the next `BL-NNN` id and a `[planned]`
status. Move to `[in-progress]` / `[done]` as work lands.

## Tests

- `make check` runs ruff + mypy strict + pytest. CI uses the same target.
- Unit tests live under `tests/unit/`, integration under
  `tests/integration/`, end-to-end (stdio MCP smoke) under `tests/e2e/`.
- `pytest-asyncio` is in `auto` mode, so async tests need no decorator.
- Use the `tmp_nous_home` fixture (in `tests/conftest.py`) when a test must
  write state.

## Branches and PRs

- Develop on `claude/<short-slug>` or `feature/<short-slug>` branches.
- Reference `BL-NNN` and any ADR in the PR description.
- PR description states what changed, the blast radius, and a rollback path.
- Security-relevant changes (policy, audit, runner, anthropic_client,
  estimators/base, interop/base) require an ADR and a "security note"
  paragraph in the PR.

## Boundaries

Do not change these files without an ADR:

- `src/nous/policy.py` (tier classification + admission)
- `src/nous/runner.py` (audited execution wrapper)
- `src/nous/audit.py` (JSONL append-only sink)
- `src/nous/state/machine.py` (FSM transition table)
- `src/nous/anthropic_client.py` (cap + cache discipline)
- `src/nous/estimators/base.py` (filter Protocol)
- `src/nous/interop/base.py` (adapter Protocol)
- The hardware-profile schema in `profiles/`

Never introduce a runtime dependency on a private repository. `nous` is a
standalone codebase; if a piece of infrastructure is useful, port the
shape rather than the dependency.

## Self-driving simulator mode

When a Claude session is acting as the controller in `examples/self_driving_demo.py`:

1. The controller reads `skills/nous-getting-started.md` before issuing
   tools.
2. The controller respects the Anthropic daily call cap; if the cap is
   reached, fall back to `inference_local` (the local mock).
3. The controller never asks for raw audit bodies. The audit log only
   stores hashes by design.

## Status and limitations

[STATUS.md](STATUS.md) is authoritative on phase and document maturity.
[LIMITATIONS.md](LIMITATIONS.md) is authoritative on scope boundaries.
Whenever you change behaviour that those documents describe, update them in
the same commit.

## License

Apache-2.0. By contributing you agree to the DCO (`git commit -s`).
