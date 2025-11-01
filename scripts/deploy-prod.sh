#!/bin/bash
# Deploy the monolith stack to a single Docker host (default: 18.216.19.153)
# Usage: ./scripts/deploy-prod.sh [server-host] [ssh-user]

set -euo pipefail
SERVER_HOST=${1:-${DEPLOY_SERVER_HOST:-18.216.19.153}}
SSH_USER=${2:-${DEPLOY_SSH_USER:-ubuntu}}
APP_DIR=${REMOTE_APP_DIR:-/opt/borehole}
ENV_FILE_PATH=${ENV_FILE:-.env.prod}

if [[ -z "${SERVER_HOST}" ]]; then
  cat <<EOF
Usage: ./scripts/deploy-prod.sh <server-host> [ssh-user]

Environment variables:
  DEPLOY_SERVER_HOST   Override default host (${SERVER_HOST})
  DEPLOY_SSH_USER      Override default ssh user (${SSH_USER})
  REMOTE_APP_DIR       Remote application directory (${APP_DIR})
  ENV_FILE             Local env file to upload (${ENV_FILE_PATH})
  RSYNC_OPTS           Extra rsync flags (optional)
EOF
  exit 1
fi

echo "🚀 Deploying Borehole Analysis App"
echo "   Host: ${SSH_USER}@${SERVER_HOST}"
echo "   Target directory: ${APP_DIR}"
echo ""

if ! command -v rsync >/dev/null 2>&1; then
  echo "❌ rsync not installed. Please install rsync first." >&2
  exit 1
fi

if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "${SSH_USER}@${SERVER_HOST}" "echo ok" >/dev/null 2>&1; then
  cat <<EOF
❌ Unable to connect to ${SSH_USER}@${SERVER_HOST}
- verify network access and SSH key
- or set DEPLOY_SERVER_HOST/DEPLOY_SSH_USER if different
EOF
  exit 1
fi

echo "📁 Ensuring remote directory structure exists..."
ssh "${SSH_USER}@${SERVER_HOST}" "sudo mkdir -p ${APP_DIR} && sudo chown -R ${SSH_USER}:${SSH_USER} ${APP_DIR}"
ssh "${SSH_USER}@${SERVER_HOST}" "mkdir -p ${APP_DIR}/logs ${APP_DIR}/output ${APP_DIR}/secrets"

RSYNC_EXCLUDES=(
  '--exclude=.git/'
  '--exclude=venv/'
  '--exclude=node_modules/'
  '--exclude=__pycache__/'
  '--exclude=logs/'
  '--exclude=output/'
  '--exclude=*.pyc'
)

echo "📦 Syncing project files..."
DEST="${SSH_USER}@${SERVER_HOST}:${APP_DIR}/"
# shellcheck disable=SC2086 # optional RSYNC_OPTS is intentionally unquoted
rsync -az --delete "${RSYNC_EXCLUDES[@]}" ${RSYNC_OPTS:-} ./ "$DEST"

if [[ -f "${ENV_FILE_PATH}" ]]; then
  echo "🔐 Uploading ${ENV_FILE_PATH} -> ${APP_DIR}/.env.prod"
  scp "${ENV_FILE_PATH}" "${SSH_USER}@${SERVER_HOST}:${APP_DIR}/.env.prod"
else
  echo "⚠️  ${ENV_FILE_PATH} not found locally. Expecting it to exist on the server."
fi

if [[ -f secrets/box_config.json ]]; then
  echo "📄 Uploading secrets/box_config.json"
  scp secrets/box_config.json "${SSH_USER}@${SERVER_HOST}:${APP_DIR}/secrets/box_config.json"
fi

echo "🚢 Rolling out containers..."
ssh "${SSH_USER}@${SERVER_HOST}" "bash -s ${APP_DIR}" <<'REMOTE_EOF'
set -euo pipefail

APP_DIR="$1"

cd "$APP_DIR"

if [[ ! -f .env.prod ]]; then
  echo "❌ Missing .env.prod in $APP_DIR" >&2
  exit 1
fi

ln -sf .env.prod .env

if [[ ! -f secrets/box_config.json ]]; then
  echo "⚠️  secrets/box_config.json not found. Pipeline Box access may fail." >&2
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_CMD="docker-compose"
else
  echo "❌ Docker Compose is not installed. Run scripts/setup-server.sh on the host." >&2
  exit 1
fi

echo "🛠  Building + starting containers..."
$COMPOSE_CMD -f docker-compose.prod.yml up -d --build

echo "📊 Current service status:"
$COMPOSE_CMD -f docker-compose.prod.yml ps

echo ""
echo "✅ Deployment complete"
REMOTE_EOF

echo ""
echo "🌐 Application should be available at: http://${SERVER_HOST}/"
echo "💡 Tip: ensure the server has pull access to Box and secrets configured."

