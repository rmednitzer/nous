#!/usr/bin/env bash
# Auto-update nous to origin/main.
#
# Idempotent; safe to re-run. Run from systemd via nous-auto-update.timer
# every few minutes. If origin/main has not moved, exits 0 with no log
# entry beyond the systemd record. If it has, fast-forwards the working
# tree, re-runs the installer (picks up any new deps), restarts the
# service, and sanity-checks that the new process came up active.
#
# Failure modes:
#   - git fetch failure: exits non-zero; timer retries on next tick.
#   - install.sh failure: exits non-zero; the previous nous.service
#     keeps running with the previous code.
#   - nous.service refuses to come up: exits non-zero; the broken
#     restart already happened; manual triage required (see
#     docs/deployment.md or skills/nous-operations.md).

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/nous}"
LOG_FILE="${LOG_FILE:-/var/log/nous/auto-update.log}"

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
    exit 1
fi

log "active at ${REMOTE:0:12}"
