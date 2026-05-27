#!/usr/bin/env bash
# Auto-update nous to origin/main.
#
# Idempotent; safe to re-run. Run from systemd via nous-auto-update.timer
# every few minutes. If origin/main has not moved, exits 0 with no log
# entry beyond the systemd record. If it has, fast-forwards the working
# tree, re-runs the installer (picks up any new deps), restarts the
# service, and sanity-checks that the new process came up active.
#
# Closes AUDIT-2026-05-20 H8 (rollback discipline). On a successful
# update the script appends the new HEAD to /var/log/nous/auto-update.last_ok;
# on a failed post-restart sanity check it appends the broken HEAD to
# /var/log/nous/auto-update.last_failed and refuses to re-attempt that
# commit on subsequent ticks, breaking the every-five-minutes retry loop.
# deploy/auto-update-rollback.sh reads last_ok to roll the working tree
# back to the previous known-good commit.
#
# Failure modes:
#   - git fetch failure: exits non-zero; timer retries on next tick.
#   - install.sh failure: exits non-zero; the previous nous.service
#     keeps running with the previous code.
#   - nous.service refuses to come up: the broken commit SHA is
#     recorded in last_failed so subsequent ticks skip it; manual
#     triage and rollback via deploy/auto-update-rollback.sh.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/nous}"
LOG_DIR="${LOG_DIR:-/var/log/nous}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/auto-update.log}"
LAST_OK_FILE="${LAST_OK_FILE:-${LOG_DIR}/auto-update.last_ok}"
LAST_FAILED_FILE="${LAST_FAILED_FILE:-${LOG_DIR}/auto-update.last_failed}"

stamp() { date -u +%FT%TZ; }
log() { echo "[$(stamp)] $*" | tee -a "${LOG_FILE}"; }

cd "${REPO_DIR}"

git fetch --quiet origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "${LOCAL}" = "${REMOTE}" ]; then
    # No change; quiet exit, no log entry.
    exit 0
fi

# Break the retry loop on a known-broken commit. The last_failed
# file is a structured allowlist of "do not re-attempt": one line
# per failure with the broken SHA. The check refuses to redeploy
# REMOTE if it appears anywhere in the file. An operator clears
# last_failed (or runs deploy/auto-update-rollback.sh) to re-enable
# auto-update once they have triaged.
if [ -f "${LAST_FAILED_FILE}" ] && grep -q -F " ${REMOTE} " "${LAST_FAILED_FILE}" 2>/dev/null; then
    log "skipping ${REMOTE:0:12}: previously failed; see ${LAST_FAILED_FILE}"
    exit 0
fi

log "updating ${LOCAL:0:12} -> ${REMOTE:0:12}"
log "subject: $(git log -1 --pretty=%s "${REMOTE}")"

git reset --hard "${REMOTE}"

bash "${REPO_DIR}/deploy/install.sh"

systemctl daemon-reload
systemctl restart nous.service

# Give uvicorn a moment to bind, then assert it actually came up.
sleep 3
if ! systemctl is-active --quiet nous.service; then
    log "ERROR nous.service is not active after restart"
    systemctl --no-pager status nous.service | head -20 | sed "s/^/  /" >> "${LOG_FILE}"
    # Record the broken commit so the next tick refuses to re-deploy
    # it. Format: "<timestamp> <broken_sha> prev=<prev_sha>".
    mkdir -p "${LOG_DIR}"
    echo "$(stamp) ${REMOTE} prev=${LOCAL}" >> "${LAST_FAILED_FILE}"
    exit 1
fi

# Record the new known-good commit. deploy/auto-update-rollback.sh
# uses the most recent line's prev= field as the rollback target.
# Format: "<timestamp> <new_sha> prev=<prev_sha>".
mkdir -p "${LOG_DIR}"
echo "$(stamp) ${REMOTE} prev=${LOCAL}" >> "${LAST_OK_FILE}"

log "active at ${REMOTE:0:12}"
