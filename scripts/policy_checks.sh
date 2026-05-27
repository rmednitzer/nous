#!/usr/bin/env bash
# Repository policy checks. Run in CI and locally before pushing.
#
# Closes AUDIT-2026-05-23 C6 (the policy greps CLAUDE.md advertises
# were not actually enforced by CI). Each rule below is a single
# grep; on a hit, the script prints the offending lines and exits
# non-zero. Keep additions surgical: one rule per stanza, one
# grep per rule, no dependencies beyond coreutils + grep with -P.

set -euo pipefail

# Force a UTF-8 locale before any grep call. ``grep -P '\x{2014}'``
# requires a UTF-8 locale to compile codepoints above 0x7F; under
# ``LC_ALL=C`` (or POSIX) grep exits 2 with "character code point
# value in \x{} or \o{} is too large" and the policy job fails closed
# even on a clean tree. ``C.UTF-8`` is universally available on glibc
# (every CI runner this script targets) and on macOS 11+.
export LC_ALL=C.UTF-8

# Project root resolves whether the script is invoked from CI
# (working directory is the repo root) or by a contributor from
# anywhere else in the tree.
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
cd "${repo_root}"

fail=0

note() {
    printf '\n[policy] %s\n' "$1"
}

# Run a grep and treat both "match found" (rc=0) and "grep error"
# (rc>=2: unsupported regex flag, IO error, etc.) as policy
# failures. Only "no match" (rc=1) is a pass. The pattern lets the
# script keep ``set -e`` and still inspect the exit code.
run_grep() {
    local label="$1"
    shift
    local rc=0
    local output=""
    output=$(grep --color=never "$@") || rc=$?
    case "${rc}" in
        0)
            printf '%s\n' "${output}"
            note "FAIL: ${label}"
            fail=1
            ;;
        1)
            : # no match -> rule passes
            ;;
        *)
            note "FAIL: ${label} (grep exited ${rc}; treating as policy failure)"
            fail=1
            ;;
    esac
}

# --- Rule: no em-dashes in markdown ----------------------------------
# CLAUDE.md "Markdown style" forbids U+2014 (em-dash) anywhere in
# prose. Use '--' to approximate, or rewrite with a comma, colon, or
# parenthetical. Source-code string literals may carry U+2014 if the
# string genuinely needs one; this check is markdown-only.
note "checking for em-dash (U+2014) in markdown"
run_grep "em-dash (U+2014) found above. Use '--' or punctuation per CLAUDE.md." \
    -rPn '\x{2014}' --include='*.md' \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=site \
    --exclude-dir=node_modules --exclude-dir=.pytest_cache .

# --- Rule: no private-repository references --------------------------
# AGENTS.md "Boundaries" forbids runtime dependencies on private
# repositories ("``nous`` is a standalone codebase"). The check is
# wired with a deny list so the contract is in code, not in prose.
# Append a bash regex below when a specific private-repo name needs to
# be banned; today the list is empty and the rule is a structured
# extension point rather than an active check.
#
# This file is excluded from the scan: every declared pattern would
# otherwise match its own deny-list entry in this script.
private_repo_patterns=(
    # "example-internal-repo"
    # "another-private-name"
)
if [ "${#private_repo_patterns[@]}" -gt 0 ]; then
    note "checking for private-repository references"
    pattern_alternation="$(IFS='|'; printf '%s' "${private_repo_patterns[*]}")"
    run_grep "private-repo reference found above. See AGENTS.md Boundaries." \
        -rEn "(${pattern_alternation})" \
        --exclude="$(basename "$0")" \
        --exclude-dir=.git --exclude-dir=.venv --exclude-dir=site \
        --exclude-dir=node_modules --exclude-dir=.pytest_cache .
fi

# --- Rule: no global numpy.random calls in src/nous -------------------
# ADR 0019 follow-up: the engine threads a single
# ``numpy.random.Generator`` through every subsystem and estimator.
# Reaching for ``np.random.rand``, ``np.random.choice`` (etc.) bypasses
# the seam and reintroduces process-global state that ADR 0019 was
# written to eliminate. Only ``np.random.Generator`` (the type) and
# ``np.random.default_rng(...)`` (the constructor used for the
# fallback in modules that accept an optional ``rng`` kwarg) are
# allowed. The rule applies to ``src/nous`` only; tests, scripts, and
# examples are free to use the global directly.
note "checking for global numpy.random calls in src/nous"
run_grep "global numpy.random call found above. Use Engine(seed=...).rng or accept an rng kwarg per ADR 0019." \
    -rPn '\b(np|numpy)\.random\.(?!Generator\b|default_rng\b)\w+' \
    --include='*.py' src/nous

if [ "${fail}" -eq 0 ]; then
    note "OK: all policy checks passed"
fi

exit "${fail}"
