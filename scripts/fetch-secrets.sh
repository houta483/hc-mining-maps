#!/bin/bash
# Fetch secrets from AWS Secrets Manager and write to .env.prod
# Run this on the server before starting docker-compose

set -e

REGION="${AWS_REGION:-us-east-2}"
SECRETS_DIR="${SECRETS_DIR:-$(pwd)}"
ENV_FILE="${ENV_FILE:-.env.prod}"
RUNTIME_SECRET_ID="${RUNTIME_SECRET_ID:-prod/borehole/runtime}"

echo "🔐 Fetching secrets from AWS Secrets Manager..."

# Fetch database secret
echo "📥 Fetching database credentials..."
DB_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id prod/borehole/db \
  --region "$REGION" \
  --query SecretString \
  --output text)

# For Docker Compose, always use 'mysql' as host (container name)
DB_HOST="mysql"
DB_PORT=$(echo "$DB_SECRET" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['port'])" 2>/dev/null || echo "3306")
DB_NAME=$(echo "$DB_SECRET" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['database'])" 2>/dev/null || echo "borehole_db")
DB_USER=$(echo "$DB_SECRET" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['username'])" 2>/dev/null || echo "borehole_user")
DB_PASSWORD=$(echo "$DB_SECRET" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['password'])" 2>/dev/null || echo "")

# Fetch JWT secret
echo "📥 Fetching JWT secret..."
JWT_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id prod/borehole/jwt \
  --region "$REGION" \
  --query SecretString \
  --output text)

JWT_SECRET_KEY=$(echo "$JWT_SECRET" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['secret_key'])" 2>/dev/null || echo "")

# Fetch Mapbox token
echo "📥 Fetching Mapbox token..."
MAPBOX_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id prod/borehole/mapbox \
  --region "$REGION" \
  --query SecretString \
  --output text)

MAPBOX_TOKEN=$(echo "$MAPBOX_SECRET" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['token'])" 2>/dev/null || echo "")

# Fetch Box config
echo "📥 Fetching Box configuration..."
BOX_CONFIG=$(aws secretsmanager get-secret-value \
  --secret-id prod/borehole/box \
  --region "$REGION" \
  --query SecretString \
  --output text)

# Write Box config to file
mkdir -p "$SECRETS_DIR/secrets"
echo "$BOX_CONFIG" > "$SECRETS_DIR/secrets/box_config.json"
chmod 600 "$SECRETS_DIR/secrets/box_config.json"
echo "✅ Box config written to $SECRETS_DIR/secrets/box_config.json"

# Fetch runtime configuration (optional)
BOX_PARENT_FOLDER_ID=""
BOX_MINE_AREAS_JSON=""
PIPELINE_REFRESH_SECONDS="600"

echo "📥 Fetching runtime pipeline settings (optional)..."
if RUNTIME_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id "$RUNTIME_SECRET_ID" \
  --region "$REGION" \
  --query SecretString \
  --output text 2>/dev/null); then
  BOX_PARENT_FOLDER_ID=$(RUNTIME_SECRET="$RUNTIME_SECRET" python3 - <<'PY'
import json
import os
secret = json.loads(os.environ["RUNTIME_SECRET"])
parent = secret.get("parent_folder_id", "")
print(parent, end="")
PY
  )
  BOX_MINE_AREAS_JSON=$(RUNTIME_SECRET="$RUNTIME_SECRET" python3 - <<'PY'
import json
import os
secret = json.loads(os.environ["RUNTIME_SECRET"])
mine_areas = secret.get("mine_areas")
if mine_areas:
    print(json.dumps(mine_areas, separators=(",", ":")), end="")
else:
    print("", end="")
PY
  )
  PIPELINE_REFRESH_SECONDS_RAW=$(RUNTIME_SECRET="$RUNTIME_SECRET" python3 - <<'PY'
import json
import os
secret = json.loads(os.environ["RUNTIME_SECRET"])
value = secret.get("refresh_seconds")
if value is None:
    print("", end="")
else:
    print(str(value), end="")
PY
  )
  if [ -n "$PIPELINE_REFRESH_SECONDS_RAW" ]; then
    PIPELINE_REFRESH_SECONDS="$PIPELINE_REFRESH_SECONDS_RAW"
  fi
  echo "✅ Runtime settings loaded from $RUNTIME_SECRET_ID"
else
  echo "ℹ️  Runtime secret $RUNTIME_SECRET_ID not found; using defaults"
fi

# Write .env.prod file
cat > "$ENV_FILE" <<EOF
# Database Configuration
MYSQL_ROOT_PASSWORD=${DB_PASSWORD}
MYSQL_DATABASE=${DB_NAME}
MYSQL_USER=${DB_USER}
MYSQL_PASSWORD=${DB_PASSWORD}

# API Configuration
JWT_SECRET_KEY=${JWT_SECRET_KEY}

# Frontend Configuration
MAPBOX_TOKEN=${MAPBOX_TOKEN}

# AWS Configuration
AWS_REGION=${REGION}

# Application Configuration
CORS_ORIGINS=*
DEBUG_MODE=false
BOX_PARENT_FOLDER_ID=${BOX_PARENT_FOLDER_ID}
BOX_MINE_AREAS_JSON=${BOX_MINE_AREAS_JSON}
PIPELINE_REFRESH_SECONDS=${PIPELINE_REFRESH_SECONDS}
EOF

echo "✅ Secrets written to $ENV_FILE"
echo ""
echo "⚠️  Note: $ENV_FILE contains sensitive data. Do not commit to git!"

export MYSQL_ROOT_PASSWORD=${DB_PASSWORD}
export MYSQL_DATABASE=${DB_NAME}
export MYSQL_USER=${DB_USER}
export MYSQL_PASSWORD=${DB_PASSWORD}
export JWT_SECRET_KEY=${JWT_SECRET_KEY}
export MAPBOX_TOKEN=${MAPBOX_TOKEN}
export AWS_REGION=${REGION}
export BOX_PARENT_FOLDER_ID=${BOX_PARENT_FOLDER_ID}
export BOX_MINE_AREAS_JSON=${BOX_MINE_AREAS_JSON}
export PIPELINE_REFRESH_SECONDS=${PIPELINE_REFRESH_SECONDS}

