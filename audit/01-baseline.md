# Audit 01: Validation Baseline

Read-only baseline captured before any remediation. This is the regression
reference for every later change in this pass. All figures come from commands
run in this session, named inline.

- Date: 2026-06-13
- Revision: `6e6d8127ad709f45098d637ca61ec355b8193226`
- Environment: `uv` provisions the resolved 3.12+ venv for every target.

## Clean build / install

```
uv sync --all-extras
```

Outcome: success. Resolved and installed the full dependency set (dev, docs,
prod extras). No build errors. The package itself is installed editable
(`-e .`).

## Test suite

```
uv run pytest        # asyncio_mode=auto, testpaths=tests, addopts=-q
```

Outcome: **812 passed in 22.77 s** (a second run: 31.3 s wall including
collection). Zero failures, zero errors, zero skips reported in the summary
line. No xfail/xpass surfaced.

- Flaky candidates: none observed across two consecutive runs (812/812 both
  times). The suite seeds no wall-clock dependence visible in the summary;
  property tests use Hypothesis with its own determinism controls.
- Runtime: ~23-31 s single-process. Acceptable as a local pre-push gate.

Test layout: 52 unit + 25 integration `test_*.py` files (`find tests -name
'test_*.py'`).

## Coverage

No coverage tool is configured (`pytest-cov` is absent from the dev extra;
no `.coveragerc` / `[tool.coverage]`). Coverage was therefore not measured
in this pass. This is recorded as an observation, not a defect; see audit 02
quality register (Q-tooling) for the backlog proposal. `[UNVERIFIED]` line/
branch coverage percentage.

## Lint / format / type

```
uv run ruff check .          # All checks passed!
uv run ruff format --check . # 80 files would be reformatted, 92 already formatted
uv run mypy                  # Success: no issues found in 162 source files
```

- `ruff check`: clean.
- `ruff format --check`: reports 80 files that differ from `ruff format`
  output. CI does **not** run `ruff format --check` (the `check` job runs
  `make check` = lint + typecheck + test only; `make format` is a manual,
  mutating target). So this is drift, not a CI break. A blanket reformat
  would touch 80 files (large blast radius, no behavior change); deferred to
  backlog rather than executed in this pass. Recorded as Q-FORMAT in audit 02.
- `mypy --strict`: clean across 162 files (src + tests).

## Policy gate

```
bash scripts/policy_checks.sh
```

Outcome: OK. Em-dash (U+2014) ban and global-`numpy.random` ban both pass;
private-repo deny list clean.

## Docs build

```
uv run mkdocs build --strict
```

Outcome: success, built in ~2.4 s, no strict warnings (no broken internal
links, no missing nav entries).

## Supply-chain / security tooling (baseline snapshot)

Run here so the security phase has a baseline; detail in audit 02.

```
uv tool run --from pip-audit pip-audit --strict --disable-pip --no-deps -r <exported reqs>
uv tool run --from bandit bandit -r src/nous
gitleaks detect --no-banner --redact
```

- pip-audit: **No known vulnerabilities found** across the exported project
  requirements (175 pinned lines).
- bandit: **0 issues** at every severity/confidence (10,549 LOC scanned, 0
  `#nosec` suppressions).
- gitleaks: **no leaks** across 49 commits of full history.

## CI parity

The local gates reproduce the CI `check` and `policy` jobs faithfully:
`make check` and `make policy` both pass locally. The `supply-chain` job
(pip-audit + bandit) also reproduced clean. The only environmental drift is
the interpreter (local 3.11 venv host vs CI 3.14), masked by `uv run`
selecting the resolved 3.12+ environment; no behavioral drift observed.

## Baseline summary table

| Gate | Result |
|------|--------|
| `uv sync` | pass |
| pytest | 812 passed, 0 failed |
| ruff check | clean |
| ruff format --check | 80 files drift (not CI-enforced) |
| mypy --strict | clean (162 files) |
| policy_checks.sh | pass |
| mkdocs --strict | pass |
| pip-audit | 0 vulns |
| bandit | 0 issues |
| gitleaks | 0 leaks |
