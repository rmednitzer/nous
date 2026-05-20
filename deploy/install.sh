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
    python3 -m venv "${VENV_DIR}"
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

# Audit log lives outside NOUS_HOME so logrotate can manage it cleanly.
# /var/log/nous/audit.jsonl is the spec path (matches deploy/logrotate.conf
# and the NOUS_AUDIT_PATH set in cloud-init.yaml).
AUDIT_DIR=/var/log/nous
AUDIT_FILE="${AUDIT_DIR}/audit.jsonl"
install -d -m 0750 -o nous -g nous "${AUDIT_DIR}"
if [ ! -f "${AUDIT_FILE}" ]; then
    sudo -u nous touch "${AUDIT_FILE}"
    chmod 0640 "${AUDIT_FILE}"
fi
chattr +a "${AUDIT_FILE}" 2>/dev/null || true

echo "nous installer done."
