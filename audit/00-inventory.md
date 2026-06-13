# Audit 00: Recon and Inventory

Read-only reconnaissance pass. Every figure below is backed by a command run
in this session; the command is named inline.

- Date: 2026-06-13
- Repository: `nous` (rmednitzer/nous)
- Revision audited: `6e6d8127ad709f45098d637ca61ec355b8193226`
  (`git log -1 --format=%H`)
- Working branch: `claude/nice-wozniak-py2l5n` (session-designated; the
  mission's nominal `audit/2026-06-13-full-pass` name is recorded here for
  traceability, but the harness pins this session to the branch above and
  forbids pushing elsewhere).

## Toolchain actually available

Captured with `python --version`, `uv --version`, etc.

| Tool | Version |
|------|---------|
| Python | 3.11.15 (repo targets >=3.12; CI runs 3.14) |
| uv | 0.8.17 |
| node | 22.22.2 |
| ruff | 0.15.8 (CLI) / 0.15.16 (project-pinned, via `uv run`) |
| mypy | 1.19.1 |
| pytest | 9.0.2 (project resolves 9.0.x) |
| gitleaks | present (`/usr/bin/gitleaks`) |
| bandit, pip-audit | fetched on demand via `uv tool run` |
| semgrep | not installed; OWASP pass done manually (see audit 02) |

Note: the local interpreter is 3.11 while the project requires >=3.12. All
`make` targets run under `uv run`, which provisions the resolved 3.12+
environment, so this did not block the build. CI pins 3.14.

## Component map

`nous` is a single Python package (`src/nous`) exposing an MCP tool surface
over a tick-driven simulator. Layout (`find src -name '*.py'`):

- Spine: `engine.py`, `tick.py`, `policy.py`, `runner.py`, `audit.py`,
  `audit_anchor.py`, `server.py`, `db.py`, `config.py`, `types.py`,
  `clocks.py`, `cli.py`, `__main__.py`.
- Cloud path: `anthropic_client.py`, `anthropic_status.py`,
  `inference_fallback.py`.
- `subsystems/` (11 physics models): power, apu, thermal, compute, storage,
  sensors, position, biometrics, comms, inference, plus `base.py`.
- `estimators/` (per-channel filters): position, power, thermal, biometrics,
  comms, compute, apu, sensors, storage, plus `base.py`.
- `self_model/`: assess, explain, viability, situation.
- `interop/`: cot, sensorthings, misb_klv, nmea0183, stanag_4774, mqtt, base.
- `state/`: machine (FSM), operator_state, comms_state.
- `scenarios/`: loader, injectors, runner, session.
- `safety/`: enforcer.
- `auth/`: oauth (file-backed issuer).
- `tools/`: MCP handler modules (audit, inference, interop, meta, publish,
  scenarios, self_model, state, subsystems).

Counts (`find ... | wc -l`, `wc -l`):

- 77 Python source files under `src/`, 12,810 physical lines.
- 77 `test_*.py` files (52 unit + 25 integration); 85 `.py` total under
  `tests/`.
- 4 hardware profiles under `profiles/`; 7 scenario YAMLs under `scenarios/`.

## Build system and entry points

- Build backend: hatchling (`pyproject.toml [build-system]`).
- Entry point: `nous = nous.cli:main` (`[project.scripts]`).
- Task runner: `Makefile` (install, lint, format, typecheck, test, check,
  policy, schema, docs-build, serve).
- Persistence: SQLite via SQLModel/SQLAlchemy; Alembic migrations under
  `alembic/` with baseline `0001`. `alembic.ini` present.
- Docs: MkDocs Material (`mkdocs.yml`), built `--strict` in CI.

## CI and IaC

- `.github/workflows/ci.yml`: three jobs (check = ruff+mypy+pytest; policy =
  em-dash and private-repo greps; supply-chain = pip-audit + bandit). All
  third-party actions are SHA-pinned. `permissions: contents: read` set at
  workflow scope.
- `.github/workflows/docs.yml`: docs build/publish.
- `deploy/`: `cloud-init.yaml`, six systemd units (service + timers for
  state-flush and auto-update), `Caddyfile.example`, `logrotate.conf`,
  `install.sh`, `auto-update.sh`, `auto-update-rollback.sh`.
- Dependency automation: `renovate.json5`.

## Dependency graph summary

- Direct runtime deps: 17 (`pyproject.toml [project.dependencies]`); the 53
  count from a naive grep includes optional-group and classifier lines.
  Optional groups: dev, docs, prod.
- Total resolved packages in `uv.lock`: 323 (`grep -c 'name = ' uv.lock`).
- Lockfile state: present and consistent (`uv sync --all-extras` resolved
  with no changes; `uv export` produced 175 pinned project requirements for
  the audit).
- Notable runtime deps: `mcp>=1.27`, `pydantic>=2.11`, `sqlmodel`,
  `alembic`, `anthropic>=0.105.2`, `numpy`, `filterpy`, `pynmea2`,
  `paho-mqtt`, `httpx`, `starlette`/`uvicorn`, `opentelemetry-api`.

## Governance artifacts already present

The repo carries an unusually deep self-audit trail, relevant because this
pass should not duplicate it: root `AUDIT.md` (2026-05-20 baseline) plus
dated audits in `docs/` through 2026-06-06; 40 accepted ADRs under
`docs/adr/` (numbered 0001-0041, with ADR 0008 superseded by 0016), plus the
two this pass proposes (0042, 0043); `docs/backlog.md` (BL-NNN tracker);
STATUS.md, LIMITATIONS.md,
SECURITY.md, CONTRIBUTING.md, CODE_OF_CONDUCT.md, LICENSE, NOTICE,
REUSE.toml. This audit is dated 2026-06-13 and continues that cadence.
