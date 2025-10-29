#!/bin/bash
# One-command deployment script for borehole analysis app (Docker Compose on server)
# Usage: ./scripts/deploy-prod.sh [server-host] [ssh-user]

set -e

echo "🚀 Borehole Analysis App - Production Deployment"
echo "================================================="

# Configuration
REGION="${AWS_REGION:-us-east-2}"
ACCOUNT_ID="553165044639"
ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Get current git SHA for image tag
IMAGE_TAG=$(git rev-parse HEAD)
echo "📌 Using image tag: $IMAGE_TAG"

# Get server connection details
SERVER_HOST="${1:-${DEPLOY_SERVER_HOST}}"
SSH_USER="${2:-${DEPLOY_SSH_USER:-ubuntu}}"

if [ -z "$SERVER_HOST" ]; then
    echo "❌ Error: Server host not provided"
    echo ""
    echo "Usage: ./scripts/deploy-prod.sh <server-host> [ssh-user]"
    echo "   Or set environment variables:"
    echo "   export DEPLOY_SERVER_HOST=your-server-ip-or-domain"
    echo "   export DEPLOY_SSH_USER=ubuntu"
    exit 1
fi

echo "📡 Server: $SSH_USER@$SERVER_HOST"
echo ""

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

MAX_WAIT_TIME=300  # 5 minutes
WAIT_INTERVAL=10   # 10 seconds
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT_TIME ]; do
    if check_image_exists "borehole-frontend" && \
       check_image_exists "borehole-backend" && \
       check_image_exists "borehole-pipeline"; then
        echo "✅ All images are ready!"
        break
    fi
    
    if [ $ELAPSED -eq 0 ]; then
        echo "   Waiting for GitHub Actions to build images..."
        echo "   (This may take a few minutes if build is still running)"
    fi
    
    echo "   Still waiting... (${ELAPSED}s elapsed)"
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ $ELAPSED -ge $MAX_WAIT_TIME ]; then
    echo "❌ Timeout waiting for images."
    echo "   Please ensure GitHub Actions workflow completed successfully."
    echo "   Or use: git push origin master to trigger build"
    exit 1
fi

# Test SSH connection
echo ""
echo "🔌 Testing SSH connection..."
if ! ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$SSH_USER@$SERVER_HOST" "echo 'Connection successful'" 2>/dev/null; then
    echo "❌ Cannot connect to server via SSH"
    echo "   Please ensure:"
    echo "   - Server is running and accessible"
    echo "   - SSH key is configured (~/.ssh/id_rsa or specify with -i)"
    echo "   - Security group allows SSH (port 22) from your IP"
    exit 1
fi
echo "✅ SSH connection successful"

# Deploy to server
echo ""
echo "📦 Deploying to server..."

# Create deployment script to run on server
DEPLOYMENT_SCRIPT=$(cat <<'DEPLOY_EOF'
#!/bin/bash
set -e

REGION="${1:-us-east-2}"
ACCOUNT_ID="${2:-553165044639}"
IMAGE_TAG="${3}"
APP_DIR="${4:-/opt/borehole}"

cd "$APP_DIR" || { echo "❌ App directory not found: $APP_DIR"; exit 1; }

echo "📥 Logging in to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

echo "📥 Pulling latest images..."
docker pull ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/borehole-frontend:${IMAGE_TAG}
docker pull ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/borehole-backend:${IMAGE_TAG}
docker pull ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/borehole-pipeline:${IMAGE_TAG}

echo "📝 Updating environment variables..."
export ECR_REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
export IMAGE_TAG="${IMAGE_TAG}"

# Fetch secrets if fetch-secrets.sh exists
if [ -f scripts/fetch-secrets.sh ]; then
    echo "🔐 Fetching secrets from AWS Secrets Manager..."
    bash scripts/fetch-secrets.sh
    export $(grep -v '^#' .env.prod | xargs)
fi

echo "🚀 Starting services..."
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d

echo "⏳ Waiting for services to start..."
sleep 10

echo "📊 Service status:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "✅ Deployment complete!"
DEPLOY_EOF
)

# Copy files to server
echo "📤 Copying files to server..."
ssh "$SSH_USER@$SERVER_HOST" "mkdir -p /opt/borehole/{config,database,scripts,deploy}" || true

# Copy necessary files
scp docker-compose.prod.yml "$SSH_USER@$SERVER_HOST:/opt/borehole/" > /dev/null
scp database/init.sql "$SSH_USER@$SERVER_HOST:/opt/borehole/database/" > /dev/null
scp deploy/nginx.conf "$SSH_USER@$SERVER_HOST:/opt/borehole/deploy/" > /dev/null
scp scripts/fetch-secrets.sh "$SSH_USER@$SERVER_HOST:/opt/borehole/scripts/" > /dev/null
scp -r config/ "$SSH_USER@$SERVER_HOST:/opt/borehole/" > /dev/null 2>&1 || echo "⚠️  config/ not copied (may need manual setup)"

# Ensure fetch-secrets.sh is executable
ssh "$SSH_USER@$SERVER_HOST" "chmod +x /opt/borehole/scripts/fetch-secrets.sh" 2>/dev/null || true

# Copy and run deployment script
echo "$DEPLOYMENT_SCRIPT" | ssh "$SSH_USER@$SERVER_HOST" "cat > /tmp/deploy.sh && chmod +x /tmp/deploy.sh && bash /tmp/deploy.sh $REGION $ACCOUNT_ID $IMAGE_TAG /opt/borehole"

echo ""
echo "================================================="
echo "✅ Deployment complete!"
echo ""
echo "Application should be running at:"
echo "  http://$SERVER_HOST"
echo ""
echo "To check status:"
echo "  ssh $SSH_USER@$SERVER_HOST 'cd /opt/borehole && docker-compose -f docker-compose.prod.yml ps'"
echo ""
echo "To view logs:"
echo "  ssh $SSH_USER@$SERVER_HOST 'cd /opt/borehole && docker-compose -f docker-compose.prod.yml logs -f'"
