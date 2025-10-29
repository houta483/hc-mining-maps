#!/bin/bash
# Initial server setup script for Borehole Analysis App

set -e

echo "Setting up Borehole Analysis App server..."

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
fi

# Install Docker Compose
if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
fi

# Create directories
echo "Creating directories..."
sudo mkdir -p /opt/fmmap/{config,secrets,logs,output}
sudo mkdir -p /etc/fm

# Set permissions
echo "Setting permissions..."
sudo chown -R $USER:$USER /opt/fmmap

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/fmmap.service > /dev/null <<EOF
[Unit]
Description=Box to Google Earth Pipeline
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/fmmap
ExecStart=/usr/local/bin/docker-compose -f /opt/fmmap/deploy/docker-compose.prod.yml up -d
ExecStop=/usr/local/bin/docker-compose -f /opt/fmmap/deploy/docker-compose.prod.yml down
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Create systemd timer
sudo tee /etc/systemd/system/fmmap.timer > /dev/null <<EOF
[Unit]
Description=Run FM pipeline on interval
Requires=fmmap.service

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Unit=fmmap.service

[Install]
WantedBy=timers.target
EOF

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy box_config.json to /opt/fmmap/secrets/"
echo "2. Configure AWS credentials at /opt/fmmap/secrets/aws_credentials"
echo "3. Update config.yaml with your Box folder IDs"
echo "4. Run: sudo systemctl daemon-reload"
echo "5. Run: sudo systemctl enable --now fmmap.timer"

