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
# Failure modes (all leave the previous good build running):
#   - git fetch failure: exits non-zero before touching the tree;
#     timer retries on next tick.
#   - install.sh or daemon-reload failure (before the new build is
#     bounced into service): the EXIT trap restores HEAD and the
#     installed artifacts to the previous commit and leaves the
#     still-running service alone. The commit is NOT added to
#     last_failed, because such failures are commonly transient.
#   - nous.service failing its post-restart health check: the trap
#     reinstalls the previous good artifacts, restarts onto them, and
#     records the broken SHA in last_failed so subsequent ticks skip
#     it. HEAD is never left advanced past a failed deploy, so the
#     next tick cannot mistake a frozen box for an up-to-date one.
#     Manual triage / rollback via deploy/auto-update-rollback.sh.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/nous}"
LOG_DIR="${LOG_DIR:-/var/log/nous}"
LOG_FILE="${LOG_FILE:-${LOG_DIR}/auto-update.log}"
LAST_OK_FILE="${LAST_OK_FILE:-${LOG_DIR}/auto-update.last_ok}"
LAST_FAILED_FILE="${LAST_FAILED_FILE:-${LOG_DIR}/auto-update.last_failed}"

stamp() { date -u +%FT%TZ; }
# Logging is best-effort: a full disk or a read-only audit mount must
# never abort a deploy or, worse, a rollback (see rollback_on_failure).
log() { echo "[$(stamp)] $*" | tee -a "${LOG_FILE}" 2>/dev/null || true; }

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

# A deploy that aborts after the working tree advances must not leave
# HEAD at REMOTE while nous.service still runs the old code: the next
# tick would compute LOCAL == REMOTE, exit 0, and freeze the box on the
# stale build with no marker. On failure the trap restores both the
# working tree and the installed artifacts (units and venv, which a git
# reset alone does not undo) to LOCAL, distinguishing two phases:
#   - failure before the new build is bounced into service (install or
#     daemon-reload): the previous service is still running untouched,
#     so we restore the good artifacts but leave it running, and we do
#     NOT record last_failed. These failures are commonly transient (a
#     pip index or network hiccup) and the commit may deploy cleanly on
#     the next tick.
#   - failure at or after the restart: the new (bad) build is the
#     running unit, so we reinstall the good artifacts and restart onto
#     them, and we record the commit in last_failed because a build that
#     came up and failed its health check is proven bad.
DEPLOY_OK=0
NEW_SERVICE_STARTED=0
rollback_on_failure() {
    local rc=$?
    [ "${DEPLOY_OK}" -eq 1 ] && return 0
    # Restore HEAD before any fallible logging or mkdir. A failed install
    # can fill the disk (or the audit mount can go read-only), making the
    # log unwritable; were a log call to abort this trap under `set -e`
    # before the reset, HEAD would stay at REMOTE and the next tick would
    # refreeze on the stale build. `log` is best-effort too (see above);
    # this ordering is the belt-and-suspenders guarantee.
    local reset_ok=1
    git reset --hard "${LOCAL}" >/dev/null 2>&1 || reset_ok=0
    mkdir -p "${LOG_DIR}" 2>/dev/null || true
    if [ "${reset_ok}" -eq 0 ]; then
        log "ERROR could not reset HEAD back to ${LOCAL:0:12}; manual triage needed"
        return 0
    fi
    log "ERROR deploy of ${REMOTE:0:12} failed (rc=${rc}); rolled back to ${LOCAL:0:12}"
    # Reinstall the previous good commit's artifacts so systemd is not
    # left pointing at a half-updated unit file or venv.
    bash "${REPO_DIR}/deploy/install.sh" >/dev/null 2>&1 \
        || log "ERROR rollback install.sh failed; previous build still running, manual triage needed"
    if [ "${NEW_SERVICE_STARTED}" -eq 1 ]; then
        systemctl --no-pager status nous.service 2>/dev/null | head -20 | sed "s/^/  /" >> "${LOG_FILE}" 2>/dev/null || true
        # Format: "<timestamp> <broken_sha> prev=<prev_sha>".
        echo "$(stamp) ${REMOTE} prev=${LOCAL}" >> "${LAST_FAILED_FILE}" 2>/dev/null || true
        systemctl daemon-reload >/dev/null 2>&1 || true
        systemctl restart nous.service >/dev/null 2>&1 \
            || log "ERROR rollback restart failed; nous.service may be down"
    else
        # The previous service was never stopped; leave it running.
        systemctl daemon-reload >/dev/null 2>&1 || true
    fi
}
trap rollback_on_failure EXIT

git reset --hard "${REMOTE}"

bash "${REPO_DIR}/deploy/install.sh"

systemctl daemon-reload

# Past this point a failure means the new build was bounced into service.
NEW_SERVICE_STARTED=1
systemctl restart nous.service

# Give uvicorn a moment to bind, then assert it actually came up.
sleep 3
if ! systemctl is-active --quiet nous.service; then
    log "ERROR nous.service is not active after restart"
    exit 1
fi

# Confirmed active on the new build; disarm the rollback trap.
DEPLOY_OK=1
trap - EXIT

# Record the new known-good commit. deploy/auto-update-rollback.sh
# uses the most recent line's prev= field as the rollback target.
# Format: "<timestamp> <new_sha> prev=<prev_sha>".
mkdir -p "${LOG_DIR}"
echo "$(stamp) ${REMOTE} prev=${LOCAL}" >> "${LAST_OK_FILE}"

log "active at ${REMOTE:0:12}"
