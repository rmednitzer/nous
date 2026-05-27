#!/usr/bin/env bash
# Roll the nous working tree back to the previous known-good commit.
#
# Reads /var/log/nous/auto-update.last_ok (written by
# deploy/auto-update.sh after every successful update) and resets
# the working tree to the ``prev=`` SHA on the most recent line. Then
# re-runs install.sh and restarts nous.service.
#
# Pair with the kill-switch in SECURITY.md ("Auto-update kill
# switches"): the operator who diagnoses a bad commit on the live VM
# disables the timer, runs this script, re-enables the timer once
# the bad commit is reverted on main. The last_failed marker that
# auto-update.sh writes on a sanity-check failure is cleared so the
# rolled-back commit can attempt a re-deploy on a subsequent tick.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/nous}"
LOG_DIR="${LOG_DIR:-/var/log/nous}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/auto-update.log}"
LAST_OK_FILE="${LAST_OK_FILE:-${LOG_DIR}/auto-update.last_ok}"
LAST_FAILED_FILE="${LAST_FAILED_FILE:-${LOG_DIR}/auto-update.last_failed}"

stamp() { date -u +%FT%TZ; }
log() { echo "[$(stamp)] rollback: $*" | tee -a "${LOG_FILE}"; }

if [ ! -f "${LAST_OK_FILE}" ]; then
    log "ERROR no ${LAST_OK_FILE}; nothing to roll back to"
    exit 1
fi

# Pick the rollback target. Address PR #57 review (Codex +
# Copilot): the original parser read the ``prev=`` field of the
# most recent ``last_ok`` line, which was wrong in the failed-
# deploy case. Trace: A->B succeeds (last_ok: "T1 B prev=A"),
# B->C succeeds (last_ok: "T2 C prev=B"), C->D fails (last_failed:
# "T3 D prev=C"; HEAD at D). The intent of rollback is to return
# to C (the last successfully-deployed SHA), not B. Two equivalent
# sources for that SHA: the ``prev=`` field of the most recent
# ``last_failed`` line, or the deployed-SHA field (column 2) of
# the most recent ``last_ok`` line. We prefer ``last_failed`` when
# it has entries (it names the broken deploy explicitly), falling
# back to the last ``last_ok`` row otherwise.
TARGET=""
if [ -f "${LAST_FAILED_FILE}" ] && [ -s "${LAST_FAILED_FILE}" ]; then
    TARGET=$(awk 'END {for (i=1;i<=NF;i++) if ($i ~ /^prev=/) {split($i,a,"="); print a[2]}}' "${LAST_FAILED_FILE}")
fi
if [ -z "${TARGET}" ]; then
    TARGET=$(awk 'END {print $2}' "${LAST_OK_FILE}")
fi
if [ -z "${TARGET}" ]; then
    log "ERROR could not parse a rollback target out of ${LAST_OK_FILE}"
    exit 1
fi

cd "${REPO_DIR}"
if ! git cat-file -e "${TARGET}^{commit}" 2>/dev/null; then
    log "ERROR rollback target ${TARGET:0:12} is not present locally; fetch first"
    exit 1
fi

CURRENT=$(git rev-parse HEAD)
log "rolling ${CURRENT:0:12} -> ${TARGET:0:12}"

git reset --hard "${TARGET}"

bash "${REPO_DIR}/deploy/install.sh"

systemctl daemon-reload
systemctl restart nous.service

sleep 3
if ! systemctl is-active --quiet nous.service; then
    log "ERROR nous.service is not active after rollback; this is bad"
    systemctl --no-pager status nous.service | head -20 | sed "s/^/  /" >> "${LOG_FILE}"
    exit 1
fi

# Clear the failure marker so the timer can resume normal operation
# once the operator reverts the bad commit on main.
if [ -f "${LAST_FAILED_FILE}" ]; then
    : > "${LAST_FAILED_FILE}"
    log "cleared ${LAST_FAILED_FILE}"
fi

log "active at ${TARGET:0:12}"
