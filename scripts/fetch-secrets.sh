#!/bin/bash
# Fetch secrets from AWS Secrets Manager and write to .env.prod
# Run this on the server before starting docker-compose

set -e

REGION="${AWS_REGION:-us-east-2}"
SECRETS_DIR="${SECRETS_DIR:-$(pwd)}"
ENV_FILE="${ENV_FILE:-.env.prod}"

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
USE_LOCAL_DATA=false
DEBUG_MODE=false
EOF

echo "✅ Secrets written to $ENV_FILE"
echo ""
echo "⚠️  Note: $ENV_FILE contains sensitive data. Do not commit to git!"

