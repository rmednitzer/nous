#!/usr/bin/env bash
# Repository policy checks. Run in CI and locally before pushing.
#
# Closes AUDIT-2026-05-23 C6 (the policy greps CLAUDE.md advertises
# were not actually enforced by CI). Each rule below is a single
# grep; on a hit, the script prints the offending lines and exits
# non-zero. Keep additions surgical: one rule per stanza, one
# grep per rule, no dependencies beyond coreutils + grep with -P.

set -uo pipefail

# Project root resolves whether the script is invoked from CI
# (working directory is the repo root) or by a contributor from
# anywhere else in the tree.
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "${repo_root}"

fail=0

note() {
    printf '\n[policy] %s\n' "$1"
}

# --- Rule: no em-dashes in markdown ----------------------------------
# CLAUDE.md "Markdown style" forbids U+2014 (em-dash) anywhere in
# prose. Use '--' to approximate, or rewrite with a comma, colon, or
# parenthetical. Source-code string literals may carry U+2014 if the
# string genuinely needs one; this check is markdown-only.
note "checking for em-dash (U+2014) in markdown"
if grep --color=never -rPn '\x{2014}' --include='*.md' \
        --exclude-dir=.git --exclude-dir=.venv --exclude-dir=site \
        --exclude-dir=node_modules --exclude-dir=.pytest_cache .; then
    note "FAIL: em-dash (U+2014) found above. Use '--' or punctuation per CLAUDE.md."
    fail=1
fi

# --- Rule: no private-repository references --------------------------
# AGENTS.md "Boundaries" forbids runtime dependencies on private
# repositories ("``nous`` is a standalone codebase"). The check is
# wired with a deny list so the contract is in code, not in prose.
# Append a bash regex below when a specific private-repo name needs to
# be banned; today the list is empty and the rule is a structured
# extension point rather than an active check.
private_repo_patterns=(
    # "example-internal-repo"
    # "another-private-name"
)
if [ "${#private_repo_patterns[@]}" -gt 0 ]; then
    note "checking for private-repository references"
    pattern_alternation="$(IFS='|'; printf '%s' "${private_repo_patterns[*]}")"
    if grep --color=never -rEn "(${pattern_alternation})" \
            --exclude-dir=.git --exclude-dir=.venv --exclude-dir=site \
            --exclude-dir=node_modules --exclude-dir=.pytest_cache .; then
        note "FAIL: private-repo reference found above. See AGENTS.md Boundaries."
        fail=1
    fi
fi

if [ "${fail}" -eq 0 ]; then
    note "OK: all policy checks passed"
fi

exit "${fail}"
