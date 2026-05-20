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

# Prefer the platform Python from Ubuntu 26.04 (3.14) when present; fall
# back through 3.13 to plain python3 on 24.04 (which resolves to 3.12) so
# the bundle still works on the previous LTS.
for candidate in python3.14 python3.13 python3; do
    if command -v "${candidate}" >/dev/null 2>&1; then
        PYTHON_BIN="$(command -v "${candidate}")"
        break
    fi
done
if [ -z "${PYTHON_BIN:-}" ]; then
    echo "no python3 interpreter found on PATH" >&2
    exit 1
fi

# venv
if [ ! -d "${VENV_DIR}" ]; then
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi
"${VENV_DIR}/bin/pip" install --upgrade pip wheel
"${VENV_DIR}/bin/pip" install -e "${REPO_DIR}[prod]"

# systemd units
install -m 0644 "${REPO_DIR}/deploy/systemd/nous.service" /etc/systemd/system/nous.service
install -m 0644 "${REPO_DIR}/deploy/systemd/nous-state-flush.service" /etc/systemd/system/nous-state-flush.service
install -m 0644 "${REPO_DIR}/deploy/systemd/nous-state-flush.timer" /etc/systemd/system/nous-state-flush.timer
install -m 0644 "${REPO_DIR}/deploy/systemd/nous-auto-update.service" /etc/systemd/system/nous-auto-update.service
install -m 0644 "${REPO_DIR}/deploy/systemd/nous-auto-update.timer" /etc/systemd/system/nous-auto-update.timer
install -m 0755 "${REPO_DIR}/deploy/auto-update.sh" /opt/nous/deploy/auto-update.sh

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
