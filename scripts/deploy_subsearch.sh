#!/usr/bin/env bash
# Automated deployment helper for the Subsearch server.
# Pulls the latest code, refreshes the virtualenv, and restarts systemd.

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/subsearch}"
APP_USER="${APP_USER:-subsearch}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-subsearch}"
REPO_URL="${REPO_URL:-https://github.com/ericrosenberg1/reddit-sub-analyzer.git}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
VENV_PATH="${VENV_PATH:-$APP_DIR/.venv}"
PIP_FLAGS="${PIP_FLAGS:-}"

log() {
  printf '[%s] %s\n' "$(date --iso-8601=seconds)" "$*"
}

run_as_app_user() {
  if id "$APP_USER" >/dev/null 2>&1; then
    if [[ "$(id -u)" -eq "$(id -u "$APP_USER")" ]]; then
      "$@"
    else
      runuser -u "$APP_USER" -- "$@"
    fi
  else
    log "ERROR: user '$APP_USER' not found"
    exit 2
  fi
}

ensure_repo() {
  if [[ ! -d "$APP_DIR/.git" ]]; then
    log "Cloning repository into $APP_DIR"
    mkdir -p "$APP_DIR"
    chown -R "$APP_USER":"$APP_USER" "$APP_DIR"
    run_as_app_user git clone "$REPO_URL" "$APP_DIR"
  fi
}

update_code() {
  log "Fetching latest code for $BRANCH"
  run_as_app_user git -C "$APP_DIR" fetch --prune origin
  run_as_app_user git -C "$APP_DIR" checkout "$BRANCH"
  run_as_app_user git -C "$APP_DIR" reset --hard "origin/$BRANCH"
}

ensure_venv() {
  if [[ ! -d "$VENV_PATH" ]]; then
    log "Creating virtualenv at $VENV_PATH"
    run_as_app_user "$PYTHON_BIN" -m venv "$VENV_PATH"
  fi
}

refresh_dependencies() {
  log "Installing Python dependencies"
  run_as_app_user "$VENV_PATH/bin/python" -m pip install --upgrade pip setuptools wheel
  run_as_app_user "$VENV_PATH/bin/python" -m pip install -e "$APP_DIR" $PIP_FLAGS
}

restart_service() {
  if systemctl list-unit-files --type=service | grep -q "^$SERVICE_NAME.service"; then
    log "Restarting $SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
  else
    log "WARNING: systemd service '$SERVICE_NAME' not found; skipping restart"
  fi
}

main() {
  ensure_repo
  update_code
  ensure_venv
  refresh_dependencies
  restart_service
  log "Deployment complete"
}

main "$@"
