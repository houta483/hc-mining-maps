#!/bin/bash
# Setup server and deploy via SSM (all-in-one)
# Usage: ./scripts/setup-and-deploy-ssm.sh

set -e

echo "🚀 Borehole App - Setup & Deploy via SSM"
echo "=========================================="

REGION="${AWS_REGION:-us-east-2}"
INSTANCE_ID="${INSTANCE_ID:-i-03169bf6f17bc4a23}"

# Step 1: Setup server
echo ""
echo "📦 Step 1: Setting up server (Docker, AWS CLI, etc.)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

SETUP_COMMAND=$(cat <<'SETUP_EOF'
#!/bin/bash
set -e

echo "📦 Installing dependencies..."

# Wait for any existing apt processes to finish
while sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
    echo "   Waiting for existing apt process to finish..."
    sleep 5
done

# Update package lists
sudo apt-get update -y

# Install Docker
if ! command -v docker &> /dev/null; then
    sudo apt-get install -y docker.io
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker ubuntu
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed ($(docker --version))"
fi

# Install Docker Compose plugin
if ! command -v docker compose version &> /dev/null 2>&1; then
    sudo apt-get install -y docker-compose-plugin
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Install AWS CLI v2
if ! command -v aws &> /dev/null; then
    cd /tmp
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip -q awscliv2.zip
    sudo ./aws/install
    rm -rf aws awscliv2.zip
    echo "✅ AWS CLI installed"
else
    echo "✅ AWS CLI already installed ($(aws --version))"
fi

# Install Python 3 and unzip (needed for scripts)
sudo apt-get install -y python3 unzip || true

# Create app directory
sudo mkdir -p /opt/borehole/{config,database,scripts,deploy,logs,output,secrets}
sudo chown -R ubuntu:ubuntu /opt/borehole

echo "✅ Server setup complete!"
SETUP_EOF
)

# Encode and run setup
SETUP_B64=$(echo "$SETUP_COMMAND" | base64)

SETUP_CMD_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --parameters "commands=[
        'echo \"$SETUP_B64\" | base64 -d | sudo -u ubuntu bash'
    ]" \
    --region "$REGION" \
    --profile hcmining-prod \
    --output text \
    --query 'Command.CommandId')

echo "   Setup command ID: $SETUP_CMD_ID"
echo "   Waiting for setup to complete (2-3 minutes)..."

# Wait for setup to complete
while true; do
    STATUS=$(aws ssm get-command-invocation \
        --command-id "$SETUP_CMD_ID" \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --profile hcmining-prod \
        --query 'Status' \
        --output text 2>/dev/null || echo "Unknown")
    
    if [ "$STATUS" = "Success" ] || [ "$STATUS" = "Failed" ] || [ "$STATUS" = "Cancelled" ] || [ "$STATUS" = "TimedOut" ]; then
        break
    fi
    
    echo "   Still installing... (status: $STATUS)"
    sleep 10
done

# Check setup result
SETUP_OUTPUT=$(aws ssm get-command-invocation \
    --command-id "$SETUP_CMD_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$REGION" \
    --profile hcmining-prod \
    --query 'StandardOutputContent' \
    --output text 2>/dev/null || echo "")

if [ "$STATUS" != "Success" ]; then
    echo ""
    echo "❌ Setup failed. Error:"
    aws ssm get-command-invocation \
        --command-id "$SETUP_CMD_ID" \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --profile hcmining-prod \
        --query 'StandardErrorContent' \
        --output text 2>/dev/null || echo "Unknown error"
    exit 1
fi

echo "$SETUP_OUTPUT"
echo "✅ Server setup complete!"

# Step 2: Deploy application
echo ""
echo "🚀 Step 2: Deploying application..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Run the SSM deployment script
exec ./scripts/deploy-ssm.sh

