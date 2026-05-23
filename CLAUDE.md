# CLAUDE.md

Claude-specific addenda for working in `nous`. The primary contributor guide
is [AGENTS.md](AGENTS.md); read that first. This file collects the bits
that matter when the contributor is a Claude session.

## Quick context

`nous` simulates a backpack-class AI inference appliance. The tick loop in
`src/nous/engine.py` drives subsystem physics; estimators produce calibrated
beliefs; a self-model layer aggregates them into capability claims; the MCP
tool surface in `src/nous/server.py` exposes everything to a controller.

## Tool preferences

- Prefer `Edit` over `Write` for existing files. The blast radius of a
  surgical edit is easier to reason about than a rewrite.
- Use the `Explore` agent for codebase-wide questions before you start
  changing things. Avoid duplicating its searches in the main thread.
- Use `Plan` mode before touching `policy.py`, `runner.py`, `audit.py`,
  `state/machine.py`, `anthropic_client.py`, `estimators/base.py`, or
  `interop/base.py`. Those surfaces require an ADR.
- Reach for the `claude-api` skill whenever you touch `anthropic_client.py`
  or the prompt-cache plumbing. The skill enforces the cache discipline
  this project depends on.

## Skills available to the controller

When a Claude session is the controller, FastMCP advertises the runbooks
under `skills/` via the server's `instructions=` field. Keep the runbooks
short, action-oriented, and accurate:

- `nous-getting-started.md` -- a tour of the tool surface
- `nous-scenario-walkthrough.md` -- run a scenario end-to-end
- `nous-troubleshooting.md` -- common failure patterns
- `nous-stpa-update.md` -- how to extend the STPA artefacts
- `nous-interop-tak.md` -- CoT/TAK adapter usage
- `nous-self-model.md` -- read and interpret the self-model layer
- `nous-deployment-vm.md` -- bring up the VM deployment

## Repo purpose

The point of the simulator is to make the behaviour of a backpack
inference appliance legible to a controller: which capabilities are intact
right now, which have degraded, how long the device can sustain a given
workload, and what an estimator can honestly say about the operator and
the environment. Code that obscures that picture is worse than code that
exposes a small piece of it accurately.

## Layout (abbreviated)

```
src/nous/
  cli.py config.py policy.py audit.py runner.py server.py
  engine.py tick.py db.py anthropic_client.py types.py
  state/        machine.py operator_state.py comms_state.py
  subsystems/   power, apu, thermal, compute, storage, sensors,
                position, biometrics, comms, inference
  estimators/   position, power, thermal, biometrics, comms, compute
  self_model/   assess, explain, viability
  interop/      cot, sensorthings, misb_klv, nmea0183, stanag_4774, mqtt
  auth/         oauth (file-backed issuer)
  scenarios/    loader, injectors
```

## Conventions (Claude-specific)

The general conventions live in [AGENTS.md](AGENTS.md). The Claude-specific
notes:

- **Markdown style.** No em-dashes anywhere. Use `--` when you need to
  approximate one. Never use `--` as prose punctuation outside code spans;
  use commas, colons, or parentheses. The CI grep is **not yet wired**
  (AUDIT-2026-05-23 C6 carries this finding from the 2026-05-20
  baseline); run `! grep -rPn '\x{2014}' --include='*.md' .` locally
  until the policy job lands.
- **Code comments.** Default to none. If a comment is necessary, it answers
  *why*, never *what*. Identifier names answer *what*.
- **Long-form prose.** When you write a README, ADR, or STPA section, use
  three to five short paragraphs over a long bulleted list. The bulleted
  lists in this file are the exception, not the norm.
- **Citations.** When you cite a standard (CoT, SensorThings, MISB,
  STANAG), link the canonical source in `docs/conformance/`, not inline.

## Risk posture

High blast radius surfaces (do not change without an ADR):

- `src/nous/policy.py` -- tier classification + admission
- `src/nous/runner.py` -- audited execution wrapper
- `src/nous/audit.py` -- JSONL append-only sink
- `src/nous/state/machine.py` -- FSM transitions
- `src/nous/anthropic_client.py` -- daily cap + prompt cache
- `src/nous/estimators/base.py` -- filter Protocol
- `src/nous/interop/base.py` -- adapter Protocol
- `profiles/*.yaml` schema

Low blast radius (free to iterate):

- Tool wiring in `src/nous/server.py` (provided the tier is set correctly)
- Subsystem physics curves in profile YAML
- Scenario YAML files
- Docs (README, ADR additions, model cards, conformance posture)

## Build and test commands

```sh
make install     # uv sync --all-extras
make lint        # ruff check
make typecheck   # mypy --strict
make test        # pytest
make check       # all three above
make docs-build  # mkdocs build --strict
make serve       # python -m nous serve
```

## Working through claude.ai

When `nous` is mounted as a custom MCP server in claude.ai over HTTP, the
project ships an OAuth 2.1 issuer under `src/nous/auth/`. The deployment
guide (`docs/deployment.md`) walks through binding the issuer, enabling
single-client lockdown, and gating with Caddy. Do not invent a parallel
auth scheme in client code; the issuer is the seam.

## Status cross-references

- [STATUS.md](STATUS.md) -- maturity by phase
- [LIMITATIONS.md](LIMITATIONS.md) -- scope boundaries
- [docs/backlog.md](docs/backlog.md) -- BL-NNN tracker
- [docs/adr/](docs/adr/) -- decision records

## When uncertain

Default to:

1. preserving auditability,
2. preserving the simulator's legibility (the controller can always see
   what the device is doing and why),
3. reducing blast radius (smaller PRs, narrower contract changes),
4. writing the ADR or backlog entry first if the change crosses a boundary.
