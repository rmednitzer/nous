# Contributing

`nous` is open to contributions. The repository is small and opinionated;
the conventions below keep it that way.

## Before opening a PR

1. Read [AGENTS.md](AGENTS.md) (the cross-vendor agent guide; it is also
   the human contributor guide).
2. Run `make check` locally. Ruff, mypy in strict mode, and pytest must all
   be green.
3. Run `make docs-build` if you touched anything under `docs/` or any
   docstring that the docs site references.
4. Once `nous` is past L0, additions to public APIs must be *additive*: new
   optional parameters, new modules, or new Protocols beside the existing
   ones. Do not change an existing tool's signature without an ADR.

## Commit messages

Conventional Commits with DCO sign-off:

```
feat(server): expose self_model_assess tool

Implements the BL-018 tool wiring. Covered by tests/unit/test_server.py.

Signed-off-by: Your Name <you@example.com>
```

Type prefixes: `feat`, `fix`, `docs`, `chore`, `test`, `refactor`,
`perf`, `build`, `ci`. Use `feat!:` for a breaking change and call out the
breakage in the body. Sign off with `git commit -s`.

## Licensing

The project is Apache-2.0. By contributing you agree to the DCO and to the
project's license. The repository is REUSE 3.x compliant; the
project-wide license posture lives in `REUSE.toml`. SPDX headers on
individual files are welcome but not required.

## PR description

Include the following sections:

- **What changed.** One paragraph in plain prose.
- **Blast radius.** Which components, which contracts, and which tests
  cover the change.
- **Rollback path.** What revert looks like, and whether any migrations
  need to be undone manually.
- **Security note.** Required for changes to `policy.py`, `runner.py`,
  `audit.py`, `anthropic_client.py`, `estimators/base.py`,
  `interop/base.py`, or the hardware-profile schema. State the threat
  model implications.

## Tests

- Unit tests under `tests/unit/`, integration under `tests/integration/`,
  end-to-end (stdio MCP smoke) under `tests/e2e/`.
- `pytest-asyncio` runs in `auto` mode; async tests need no decorator.
- New tools require at least one test that exercises the audited path
  (the runner produces an audit line).

## Governance

The project has a single maintainer (`@rmednitzer`). Decision artefacts:

- Architecture decisions go in `docs/adr/` (numbered, kept short).
- Line items go in `docs/backlog.md` as `BL-NNN`.
- Material behaviour changes go in `CHANGELOG.md` under `[Unreleased]`.

## Code of conduct

Be civil; assume good faith; criticise the change, not the contributor.
The project is small enough that explicit codes of conduct have not been
necessary; the unwritten rule is that the maintainer reserves the right
to decline contributions without explanation.
