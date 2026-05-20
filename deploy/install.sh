#!/usr/bin/env bash
# Idempotent nous installer. Safe to re-run.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/nous}"
VENV_DIR="${VENV_DIR:-/opt/nous/venv}"
NOUS_HOME_DIR="${NOUS_HOME:-/var/lib/nous}"

if [ ! -d "${REPO_DIR}" ]; then
    echo "nous repo not found at ${REPO_DIR}" >&2
    exit 1
fi

# venv
if [ ! -d "${VENV_DIR}" ]; then
    python3.12 -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip wheel
"${VENV_DIR}/bin/pip" install -e "${REPO_DIR}[prod]"

# systemd units
install -m 0644 "${REPO_DIR}/deploy/systemd/nous.service" /etc/systemd/system/nous.service
install -m 0644 "${REPO_DIR}/deploy/systemd/nous-state-flush.service" /etc/systemd/system/nous-state-flush.service
install -m 0644 "${REPO_DIR}/deploy/systemd/nous-state-flush.timer" /etc/systemd/system/nous-state-flush.timer

# Caddy template (do not overwrite an edited /etc/caddy/Caddyfile)
if [ ! -f /etc/caddy/Caddyfile ]; then
    install -m 0644 "${REPO_DIR}/deploy/Caddyfile.example" /etc/caddy/Caddyfile
fi

# logrotate
install -m 0644 "${REPO_DIR}/deploy/logrotate.conf" /etc/logrotate.d/nous

# OAuth state dir (clients.json / codes.json / tokens.json live here)
# The MCP SDK signs tokens internally; no signing key file needed.
install -d -m 0750 -o nous -g nous "${NOUS_HOME_DIR}/auth"

# Append-only on the audit log once it exists (no-op if not present)
if [ -f "${NOUS_HOME_DIR}/audit.jsonl" ]; then
    chattr +a "${NOUS_HOME_DIR}/audit.jsonl" || true
fi

echo "nous installer done."
