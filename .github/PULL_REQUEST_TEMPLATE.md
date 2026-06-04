## What changed

<!-- One paragraph in plain prose. -->

## Blast radius

<!-- Which components, which contracts, and which tests cover them. -->

## Rollback path

<!-- What a revert looks like, and whether any migrations or data changes are involved. -->

## Security note

<!-- Required for changes to policy.py, runner.py, audit.py, state/machine.py,
     anthropic_client.py, estimators/base.py, or interop/base.py. Otherwise "n/a". -->

## Checklist

- [ ] Follows [AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md)
- [ ] `make check` passes (ruff, mypy --strict, pytest)
- [ ] `make policy` is clean (no em-dashes in Markdown)
- [ ] High blast radius surfaces are unchanged, or an ADR accompanies the change
- [ ] Docs updated where behavior changed (README, ADR, model cards)
