#!/bin/bash
# Initial server setup script
# Run this once on a fresh EC2 server to prepare it for deployment

set -e

echo "🚀 Setting up server for Borehole Analysis App deployment"
echo "=========================================================="

# Check if running on Ubuntu/Debian or Amazon Linux
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "❌ Cannot detect OS. This script supports Ubuntu/Debian and Amazon Linux."
    exit 1
fi

echo ""
echo "📦 Installing Docker..."

if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
    # Ubuntu/Debian
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-plugin
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker $USER
elif [ "$OS" = "amzn" ] || [ "$OS" = "amazon" ]; then
    # Amazon Linux
    sudo yum update -y
    sudo yum install -y docker
    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker $USER
else
    echo "⚠️  OS not recognized. Please install Docker manually."
    exit 1
fi

echo "✅ Docker installed"

# Install Docker Compose (standalone)
echo ""
echo "📦 Installing Docker Compose..."
DOCKER_COMPOSE_VERSION="v2.24.0"
sudo curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" \
    -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
echo "✅ Docker Compose installed"

# Install AWS CLI if not present
if ! command -v aws &> /dev/null; then
    echo ""
    echo "📦 Installing AWS CLI..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
        unzip awscliv2.zip
        sudo ./aws/install
        rm -rf aws awscliv2.zip
    else
        curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
        unzip awscliv2.zip
        sudo ./aws/install
        rm -rf aws awscliv2.zip
    fi
    echo "✅ AWS CLI installed"
fi

# Create application directory
APP_DIR="/opt/borehole"
echo ""
echo "📁 Creating application directory: $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown $USER:$USER "$APP_DIR"

# Create subdirectories
mkdir -p "$APP_DIR/config" "$APP_DIR/logs" "$APP_DIR/output" "$APP_DIR/secrets" "$APP_DIR/database" "$APP_DIR/scripts"

echo "✅ Directory structure created"

# Install Python 3 (for secrets parsing)
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "📦 Installing Python 3..."
    if [ "$OS" = "ubuntu" ] || [ "$OS" = "debian" ]; then
        sudo apt-get install -y python3 python3-pip
    else
        sudo yum install -y python3 python3-pip
    fi
    echo "✅ Python 3 installed"
fi

echo ""
echo "=========================================================="
echo "✅ Server setup complete!"
echo ""
echo "Next steps:"
echo "1. Configure AWS credentials (or use IAM role)"
echo "2. Copy application files to $APP_DIR"
echo "3. Run fetch-secrets.sh to get credentials"
echo "4. Run deploy-prod.sh from your local machine"
echo ""
echo "To configure AWS credentials, run:"
echo "  aws configure --profile hcmining-prod"
echo ""
echo "Or attach an IAM role to this EC2 instance with:"
echo "  - ECR read permissions"
echo "  - Secrets Manager read permissions"







