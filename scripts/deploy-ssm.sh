#!/bin/bash
# Deploy via AWS Systems Manager (when SSH not available)
# Usage: ./scripts/deploy-ssm.sh

set -e

echo "🚀 Borehole Analysis App - Production Deployment (via SSM)"
echo "================================================="

# Configuration
REGION="${AWS_REGION:-us-east-2}"
ACCOUNT_ID="553165044639"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
INSTANCE_ID="${INSTANCE_ID:-i-03169bf6f17bc4a23}"
APP_DIR="/opt/borehole"

# Get current git SHA for image tag
IMAGE_TAG=$(git rev-parse HEAD)
echo "📌 Using image tag: $IMAGE_TAG"

# Wait for GitHub Actions to build and push images
echo "⏳ Checking if images are ready in ECR..."

check_image_exists() {
    local repo_name=$1
    aws ecr describe-images \
        --repository-name "$repo_name" \
        --image-ids imageTag="$IMAGE_TAG" \
        --region "$REGION" \
        --profile hcmining-prod \
        --query 'imageDetails[0].imageTags' \
        --output text 2>/dev/null | grep -q "$IMAGE_TAG"
}

if ! check_image_exists "borehole-frontend" || \
   ! check_image_exists "borehole-backend" || \
   ! check_image_exists "borehole-pipeline"; then
    echo "❌ Not all images are ready in ECR"
    echo "   Please wait for GitHub Actions to complete:"
    echo "   https://github.com/houta483/hc-mining-maps/actions"
    exit 1
fi

echo "✅ All images are ready!"

# Create deployment package
echo ""
echo "📦 Preparing deployment package..."

TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Copy files to temp directory
mkdir -p "$TEMP_DIR/config" "$TEMP_DIR/database" "$TEMP_DIR/scripts" "$TEMP_DIR/deploy"
cp docker-compose.prod.yml "$TEMP_DIR/"
cp database/init.sql "$TEMP_DIR/database/" 2>/dev/null || true
cp deploy/nginx.conf "$TEMP_DIR/deploy/" 2>/dev/null || true
cp scripts/fetch-secrets.sh "$TEMP_DIR/scripts/" 2>/dev/null || true
cp -r config/* "$TEMP_DIR/config/" 2>/dev/null || true

# Create deployment script
cat > "$TEMP_DIR/deploy.sh" <<DEPLOY_EOF
#!/bin/bash
set -e

REGION="${REGION}"
ACCOUNT_ID="${ACCOUNT_ID}"
IMAGE_TAG="${IMAGE_TAG}"
APP_DIR="${APP_DIR}"
ECR_REGISTRY="${ECR_REGISTRY}"

echo "📦 Setting up application directory..."
sudo mkdir -p "\$APP_DIR/{config,database,scripts,deploy}"
sudo chown -R ubuntu:ubuntu "\$APP_DIR"

# Copy files (they'll be uploaded via base64)
mkdir -p "\$APP_DIR"

echo "🔧 Ensuring Docker is installed and running..."

# Install Docker if not installed
if ! command -v docker &> /dev/null; then
    echo "📦 Installing Docker..."
    sudo apt-get update -y
    sudo apt-get install -y docker.io || {
        echo "⚠️  Package install failed, trying alternative..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        rm -f get-docker.sh
    }
fi

# Create docker group if it doesn't exist
if ! getent group docker > /dev/null 2>&1; then
    echo "📦 Creating docker group..."
    sudo groupadd docker || true
fi

# Add ubuntu user to docker group
sudo usermod -aG docker ubuntu || true

# Start and enable Docker service
echo "🚀 Starting Docker service..."
sudo systemctl daemon-reload || true
sudo systemctl enable docker || true
sudo systemctl start docker || {
    echo "⚠️  Docker service start failed, checking status..."
    sudo journalctl -u docker.service --no-pager -n 20 || true
    # Try to fix dependencies
    sudo systemctl reset-failed docker || true
    sudo systemctl start docker || true
}

# Wait for Docker to be ready
sleep 3

# Determine if we need sudo for docker commands
USE_SUDO=""
if ! docker ps >/dev/null 2>&1; then
    if sudo docker ps >/dev/null 2>&1; then
        USE_SUDO="sudo "
        echo "⚠️  Using sudo for Docker commands (user not in docker group yet)"
    else
        echo "❌ Docker daemon not accessible even with sudo"
        echo "   Checking Docker status..."
        sudo systemctl status docker --no-pager || true
        exit 1
    fi
else
    echo "✅ Docker accessible without sudo"
fi

echo "📥 Logging in to ECR..."
# Check AWS credentials first
if ! aws sts get-caller-identity &>/dev/null; then
    echo "❌ AWS credentials not configured on server"
    echo "   The EC2 instance needs an IAM role with ECR permissions"
    echo "   Or configure AWS credentials manually"
    exit 1
fi

echo "   AWS Identity: \$(aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null || echo 'Unknown')"

# Get ECR login password
echo "   Getting ECR login token..."
LOGIN_PASSWORD=\$(aws ecr get-login-password --region "\$REGION" 2>&1)
if [ \$? -ne 0 ]; then
    echo "❌ Failed to get ECR login password"
    echo "   Error: \$LOGIN_PASSWORD"
    echo "   Ensure IAM role has 'ecr:GetAuthorizationToken' permission"
    exit 1
fi

# Login to ECR using password
echo "   Authenticating with ECR..."
set +e  # Don't exit on error for login attempt
echo "\$LOGIN_PASSWORD" | ${USE_SUDO}docker login --username AWS --password-stdin "\$ECR_REGISTRY" 2>&1 | grep -v "Cannot autolaunch D-Bus" | grep -v "D-Bus"
LOGIN_STATUS=\${PIPESTATUS[0]}
set -e  # Re-enable exit on error

if [ \$LOGIN_STATUS -eq 0 ]; then
    echo "   ✅ Docker login successful"
else
    echo "   ⚠️  Initial login failed (exit code: \$LOGIN_STATUS)"
    echo "   Retrying with fresh token..."
    LOGIN_PASSWORD=\$(aws ecr get-login-password --region "\$REGION")
    set +e
    echo "\$LOGIN_PASSWORD" | ${USE_SUDO}docker login --username AWS --password-stdin "\$ECR_REGISTRY" 2>&1 | grep -v "Cannot autolaunch D-Bus" | grep -v "D-Bus"
    LOGIN_STATUS=\${PIPESTATUS[0]}
    set -e
    
    if [ \$LOGIN_STATUS -ne 0 ]; then
        echo "❌ Docker login failed after retry (exit code: \$LOGIN_STATUS)"
        echo "   Trying to diagnose..."
        ${USE_SUDO}docker info >/dev/null 2>&1 && echo "   Docker daemon is running" || echo "   Docker daemon issue"
        exit 1
    fi
    echo "   ✅ Re-authentication successful"
fi

# Function to login and pull (write credentials directly to Docker config)
pull_with_login() {
    local image=\$1
    echo "   Authenticating with ECR..."
    
    # Get ECR password
    LOGIN_PASS=\$(aws ecr get-login-password --region "\$REGION" 2>&1)
    if [ \$? -ne 0 ]; then
        echo "❌ Failed to get ECR password: \$LOGIN_PASS"
        return 1
    fi
    
    # Determine Docker config location based on whether we use sudo
    if [ -n "\$USE_SUDO" ]; then
        DOCKER_CONFIG_DIR="/root/.docker"
        DOCKER_CONFIG_USER="root"
    else
        DOCKER_CONFIG_DIR="\$HOME/.docker"
        DOCKER_CONFIG_USER="\$USER"
    fi
    
    # Create Docker config directory
    sudo mkdir -p "\$DOCKER_CONFIG_DIR"
    
    # Base64 encode credentials (username:AWS, password:LOGIN_PASS)
    AUTH_STRING="AWS:\$LOGIN_PASS"
    AUTH_B64=\$(echo -n "\$AUTH_STRING" | base64 -w 0 2>/dev/null || echo -n "\$AUTH_STRING" | base64)
    
    # Write credentials directly to Docker config.json
    DOCKER_CONFIG_FILE="\$DOCKER_CONFIG_DIR/config.json"
    
    # Create or update config.json with credentials (use sudo if needed)
    if [ -f "\$DOCKER_CONFIG_FILE" ]; then
        # Update existing config
        ${USE_SUDO}python3 << PYTHON_EOF
import json
import os

config_file = "\$DOCKER_CONFIG_FILE"
registry = "\$ECR_REGISTRY"
auth_b64 = "\$AUTH_B64"

try:
    with open(config_file, 'r') as f:
        config = json.load(f)
except:
    config = {}

if 'auths' not in config:
    config['auths'] = {}

config['auths'][registry] = {
    'auth': auth_b64
}

# Ensure credHelpers is empty (don't use credential helper)
config['credHelpers'] = {}

with open(config_file, 'w') as f:
    json.dump(config, f)

print("✅ Wrote credentials to Docker config")
PYTHON_EOF
    else
        # Create new config
        ${USE_SUDO}python3 << PYTHON_EOF
import json

config = {
    'auths': {
        "\$ECR_REGISTRY": {
            'auth': "\$AUTH_B64"
        }
    },
    'credHelpers': {}
}

with open("\$DOCKER_CONFIG_FILE", 'w') as f:
    json.dump(config, f)

print("✅ Created Docker config with credentials")
PYTHON_EOF
    fi
    
    # Verify Docker can read the config
    echo "   Verifying Docker config..."
    ${USE_SUDO}docker system info 2>&1 | grep -q "Registry" && echo "   ✅ Docker can access registry info" || echo "   ⚠️  Docker info check inconclusive"
    
    # Fix ownership and permissions (only owner can read - secure!)
    if [ -n "\$USE_SUDO" ]; then
        sudo chown root:root "\$DOCKER_CONFIG_FILE"
        sudo chmod 600 "\$DOCKER_CONFIG_FILE"  # Only root can read/write
    else
        chown "\$DOCKER_CONFIG_USER:\$DOCKER_CONFIG_USER" "\$DOCKER_CONFIG_FILE" 2>/dev/null || true
        chmod 600 "\$DOCKER_CONFIG_FILE"  # Only owner can read/write
    fi
    
    # Export DOCKER_CONFIG so Docker knows where to look
    export DOCKER_CONFIG="\$DOCKER_CONFIG_DIR"
    
    # Pull image (Docker will use the config file we just wrote)
    echo "   Pulling \$image..."
    ${USE_SUDO}docker pull "\$image" 2>&1
    return \$?
}

echo "📥 Pulling images (with fresh login for each)..."
echo ""
echo "   Pulling frontend..."
pull_with_login "\$ECR_REGISTRY/borehole-frontend:\$IMAGE_TAG" || {
    echo "   Trying 'latest' tag..."
    pull_with_login "\$ECR_REGISTRY/borehole-frontend:latest" && IMAGE_TAG="latest" || {
        echo "❌ Cannot pull frontend image"
        exit 1
    }
}

echo ""
echo "   Pulling backend..."
pull_with_login "\$ECR_REGISTRY/borehole-backend:\$IMAGE_TAG" || {
    pull_with_login "\$ECR_REGISTRY/borehole-backend:latest" || {
        echo "❌ Cannot pull backend image"
        exit 1
    }
}

echo ""
echo "   Pulling pipeline..."
pull_with_login "\$ECR_REGISTRY/borehole-pipeline:\$IMAGE_TAG" || {
    pull_with_login "\$ECR_REGISTRY/borehole-pipeline:latest" || {
        echo "❌ Cannot pull pipeline image"
        exit 1
    }
}

echo ""
echo "✅ All images pulled successfully!"

echo "📝 Tagging as latest..."
${USE_SUDO}docker tag "\$ECR_REGISTRY/borehole-frontend:\$IMAGE_TAG" "\$ECR_REGISTRY/borehole-frontend:latest" || true
${USE_SUDO}docker tag "\$ECR_REGISTRY/borehole-backend:\$IMAGE_TAG" "\$ECR_REGISTRY/borehole-backend:latest" || true
${USE_SUDO}docker tag "\$ECR_REGISTRY/borehole-pipeline:\$IMAGE_TAG" "\$ECR_REGISTRY/borehole-pipeline:latest" || true

# Fetch secrets
cd "\$APP_DIR"
if [ -f scripts/fetch-secrets.sh ]; then
    echo "🔐 Fetching secrets from AWS Secrets Manager..."
    bash scripts/fetch-secrets.sh
fi

echo "🚀 Starting services..."
cd "\$APP_DIR"
export ECR_REGISTRY="\$ECR_REGISTRY"
export IMAGE_TAG="\$IMAGE_TAG"

# Load environment variables if .env.prod exists
if [ -f .env.prod ]; then
    export \$(grep -v '^#' .env.prod | xargs)
fi

${USE_SUDO}docker compose -f docker-compose.prod.yml pull || true
${USE_SUDO}docker compose -f docker-compose.prod.yml down || true
${USE_SUDO}docker compose -f docker-compose.prod.yml up -d

echo "⏳ Waiting for services to start..."
sleep 10

echo "📊 Service status:"
${USE_SUDO}docker compose -f docker-compose.prod.yml ps

echo ""
echo "✅ Deployment complete!"
DEPLOY_EOF

chmod +x "$TEMP_DIR/deploy.sh"

# Upload files via SSM (encode as base64 and decode on server)
echo "📤 Uploading files to server via SSM..."

# Upload each file
for file in docker-compose.prod.yml deploy.sh; do
    if [ -f "$TEMP_DIR/$file" ]; then
        echo "   Uploading $file..."
        base64_file=$(base64 -i "$TEMP_DIR/$file")
        aws ssm send-command \
            --instance-ids "$INSTANCE_ID" \
            --document-name "AWS-RunShellScript" \
            --parameters "commands=[
                'mkdir -p $APP_DIR',
                'echo \"$base64_file\" | base64 -d > $APP_DIR/$file',
                'chmod +x $APP_DIR/$file'
            ]" \
            --region "$REGION" \
            --profile hcmining-prod \
            --output text \
            --query 'Command.CommandId' > /dev/null
    fi
done

# Upload directory contents
for dir in config database scripts deploy; do
    if [ -d "$TEMP_DIR/$dir" ] && [ "$(ls -A $TEMP_DIR/$dir)" ]; then
        echo "   Uploading $dir/..."
        for file in "$TEMP_DIR/$dir"/*; do
            if [ -f "$file" ]; then
                filename=$(basename "$file")
                base64_file=$(base64 -i "$file")
                aws ssm send-command \
                    --instance-ids "$INSTANCE_ID" \
                    --document-name "AWS-RunShellScript" \
                    --parameters "commands=[
                        'mkdir -p $APP_DIR/$dir',
                        'echo \"$base64_file\" | base64 -d > $APP_DIR/$dir/$filename',
                        'chmod +x $APP_DIR/$dir/$filename 2>/dev/null || true'
                    ]" \
                    --region "$REGION" \
                    --profile hcmining-prod \
                    --output text \
                    --query 'Command.CommandId' > /dev/null
            fi
        done
    fi
done

echo "   Waiting for file uploads to complete..."
sleep 5

# Run deployment script
echo ""
echo "🚀 Running deployment script on server..."

COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[
        'cd $APP_DIR',
        'REGION=$REGION ACCOUNT_ID=$ACCOUNT_ID IMAGE_TAG=$IMAGE_TAG APP_DIR=$APP_DIR ECR_REGISTRY=$ECR_REGISTRY bash deploy.sh'
    ]" \
    --region "$REGION" \
    --profile hcmining-prod \
    --output text \
    --query 'Command.CommandId')

echo "   Command ID: $COMMAND_ID"
echo "   Waiting for deployment to complete (this may take 5-10 minutes)..."

# Wait for command to complete
while true; do
    STATUS=$(aws ssm get-command-invocation \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --profile hcmining-prod \
        --query 'Status' \
        --output text 2>/dev/null || echo "Unknown")
    
    if [ "$STATUS" = "Success" ] || [ "$STATUS" = "Failed" ] || [ "$STATUS" = "Cancelled" ] || [ "$STATUS" = "TimedOut" ]; then
        break
    fi
    
    echo "   Still running... (status: $STATUS)"
    sleep 10
done

# Get command output
echo ""
echo "📋 Deployment Output:"
aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$REGION" \
    --profile hcmining-prod \
    --query 'StandardOutputContent' \
    --output text

if [ "$STATUS" != "Success" ]; then
    echo ""
    echo "❌ Deployment failed. Error output:"
    aws ssm get-command-invocation \
        --command-id "$COMMAND_ID" \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --profile hcmining-prod \
        --query 'StandardErrorContent' \
        --output text
    exit 1
fi

echo ""
echo "================================================="
echo "✅ Deployment complete!"
echo ""
echo "Application should be running at:"
echo "  http://18.216.19.153"
echo ""
echo "To check status via SSM:"
echo "  aws ssm start-session --target $INSTANCE_ID --region $REGION --profile hcmining-prod"
echo "  Then run: cd $APP_DIR && docker-compose -f docker-compose.prod.yml ps"

