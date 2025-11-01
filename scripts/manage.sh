#!/bin/bash
# Unified helper for running locally or deploying to production.
# Usage:
#   ./scripts/manage.sh local            # fetch secrets and start local stack
#   ./scripts/manage.sh local:pull       # fetch secrets only (no docker-compose)
#   ./scripts/manage.sh prod             # deploy to production server via SSH + docker compose
# Environment variables:
#   ENV_FILE             Path to .env for local runs (default .env)
#   AWS_PROFILE / AWS_REGION  Used when fetching secrets
#   DEPLOY_SERVER_HOST   Override prod host (default 18.216.19.153)
#   DEPLOY_SSH_USER      Override prod user (default ubuntu)

set -euo pipefail

COMMAND=${1:-local}
ENV_FILE_PATH=${ENV_FILE:-.env}
AWS_PROFILE=${AWS_PROFILE:-}
AWS_REGION=${AWS_REGION:-us-east-2}
DEPLOY_SERVER_HOST=${DEPLOY_SERVER_HOST:-18.216.19.153}
DEPLOY_SSH_USER=${DEPLOY_SSH_USER:-ubuntu}

fetch_secrets() {
  echo "🔐 Fetching secrets into ${ENV_FILE_PATH}"
  if [ -n "$AWS_PROFILE" ]; then
    env AWS_PROFILE="$AWS_PROFILE" AWS_REGION="$AWS_REGION" ENV_FILE="$ENV_FILE_PATH" ./scripts/fetch-secrets.sh
  else
    env AWS_REGION="$AWS_REGION" ENV_FILE="$ENV_FILE_PATH" ./scripts/fetch-secrets.sh
  fi
  echo "✅ Secrets refreshed"
}

case "$COMMAND" in
  local)
    fetch_secrets
    FETCH_SECRETS=false ENV_FILE_PATH="$ENV_FILE_PATH" ./run.sh start
    ;;
  local:pull)
    fetch_secrets
    ;;
  prod)
    echo "🚀 Deploying to production: ${DEPLOY_SSH_USER}@${DEPLOY_SERVER_HOST}"
    ./scripts/deploy-prod.sh "$DEPLOY_SERVER_HOST" "$DEPLOY_SSH_USER"
    ;;
  *)
    cat <<EOF
Usage: ./scripts/manage.sh [command]

Commands:
  local         Fetch secrets and start local docker-compose stack
  local:pull    Fetch secrets only (no docker-compose)
  prod          Deploy the compose stack to the production server

Environment:
  ENV_FILE (default .env)
  AWS_PROFILE / AWS_REGION for secret fetches
  DEPLOY_SERVER_HOST (default 18.216.19.153)
  DEPLOY_SSH_USER (default ubuntu)
EOF
    exit 1
    ;;
esac
