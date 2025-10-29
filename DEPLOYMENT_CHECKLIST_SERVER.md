# Deployment Checklist - Docker Compose Server

Follow these steps to deploy the borehole analysis app to a single EC2 server using Docker Compose.

## Prerequisites

- [ ] AWS CLI installed and configured (`aws --version`)
- [ ] Access to AWS account `553165044639` (us-east-2 region)
- [ ] GitHub repository with Actions enabled
- [ ] EC2 server instance (t3.small or larger recommended)
- [ ] SSH access to server
- [ ] Box API credentials ready (`secrets/box_config.json`)

## Step 1: Create ECR Repositories

```bash
cd infra/ecr
terraform init
terraform apply
cd ../..
```

This creates:
- `borehole-frontend`
- `borehole-backend`
- `borehole-pipeline`

✅ **Expected Output:** Three ECR repositories in us-east-2.

## Step 2: Configure GitHub Secrets

In GitHub: Settings > Secrets and variables > Actions > New repository secret

Add these secrets:
- [ ] `AWS_ACCESS_KEY_ID` - Your AWS access key
- [ ] `AWS_SECRET_ACCESS_KEY` - Your AWS secret key
- [ ] `AWS_REGION` - Value: `us-east-2`
- [ ] `MAPBOX_TOKEN` - Your Mapbox access token

## Step 3: Set Up AWS Secrets Manager

Create secrets using AWS CLI (use `hcmining-prod` profile):

### Database Secret

```bash
export AWS_PROFILE=hcmining-prod

# Generate secure password
DB_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

aws secretsmanager create-secret \
  --name prod/borehole/db \
  --secret-string "{
    \"host\": \"mysql\",
    \"port\": \"3306\",
    \"database\": \"borehole_db\",
    \"username\": \"borehole_user\",
    \"password\": \"${DB_PASSWORD}\"
  }" \
  --region us-east-2
```

**Save the password** - you'll need it to create the admin user.

### JWT Secret

```bash
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

aws secretsmanager create-secret \
  --name prod/borehole/jwt \
  --secret-string "{\"secret_key\": \"${JWT_SECRET}\"}" \
  --region us-east-2
```

### Mapbox Secret

```bash
aws secretsmanager create-secret \
  --name prod/borehole/mapbox \
  --secret-string "{\"token\": \"pk.eyJ1IjoiaGNtaW5pbmc0ODMiLCJhIjoiY21jZ3Jqb2xuMGxlMTJucHM4bzdwZWF4dSJ9.WLg5xYEvQUYW5XLYORNmMA\"}" \
  --region us-east-2
```

### Box Config Secret

```bash
aws secretsmanager create-secret \
  --name prod/borehole/box \
  --secret-string "$(cat secrets/box_config.json)" \
  --region us-east-2
```

**Verify all secrets:**
```bash
aws secretsmanager list-secrets --region us-east-2 | grep borehole
```

## Step 4: Set Up EC2 Server

### 4a. Launch EC2 Instance

1. Go to AWS Console → EC2 → Launch Instance
2. Choose Ubuntu Server 22.04 LTS or Amazon Linux 2023
3. Instance type: **t3.small** (minimum)
4. Configure security group:
   - Allow SSH (22) from your IP
   - Allow HTTP (80) from anywhere (or ALB)
   - Allow HTTPS (443) from anywhere (if using SSL)
5. Launch instance
6. **Note the public IP or DNS name**

### 4b. Set Up Server (Run on EC2 instance)

SSH to your server, then run:

```bash
# Copy setup script to server
scp scripts/setup-server.sh ubuntu@YOUR_SERVER_IP:/tmp/

# SSH to server and run setup
ssh ubuntu@YOUR_SERVER_IP
sudo bash /tmp/setup-server.sh
```

Or run manually:
```bash
# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# Configure AWS credentials (or use IAM role)
aws configure --profile hcmining-prod
```

### 4c. Set Up IAM Role (Recommended)

Instead of AWS credentials, attach IAM role to EC2:

1. Create IAM role with permissions:
   - `AmazonEC2ContainerRegistryReadOnly` (for ECR)
   - `SecretsManagerReadWrite` (for secrets)
2. Attach role to EC2 instance
3. Instance will automatically use role credentials

## Step 5: Initial Server Setup

SSH to server and create application directory:

```bash
ssh ubuntu@YOUR_SERVER_IP

sudo mkdir -p /opt/borehole
sudo chown $USER:$USER /opt/borehole
cd /opt/borehole

# Create subdirectories
mkdir -p config database scripts deploy logs output secrets
```

## Step 6: Trigger GitHub Actions Build

Push code to `master` branch:

```bash
git add .
git commit -m "Initial deployment setup"
git push origin master
```

**Monitor build:** Go to GitHub > Actions tab and watch the workflow run.

Wait for all three images to be built and pushed (~5-10 minutes).

**Verify images:**
```bash
aws ecr list-images --repository-name borehole-frontend --region us-east-2 --profile hcmining-prod
```

## Step 7: Deploy Application

From your local machine:

```bash
./scripts/deploy-prod.sh YOUR_SERVER_IP ubuntu
```

Or set environment variables:
```bash
export DEPLOY_SERVER_HOST=YOUR_SERVER_IP
export DEPLOY_SSH_USER=ubuntu
./scripts/deploy-prod.sh
```

The script will:
1. Wait for images to be ready in ECR
2. Copy files to server
3. Pull latest images
4. Fetch secrets from AWS Secrets Manager
5. Start all services with docker-compose

## Step 8: Verify Deployment

1. **Check services are running:**
   ```bash
   ssh ubuntu@YOUR_SERVER_IP 'cd /opt/borehole && docker-compose -f docker-compose.prod.yml ps'
   ```

2. **Check logs:**
   ```bash
   ssh ubuntu@YOUR_SERVER_IP 'cd /opt/borehole && docker-compose -f docker-compose.prod.yml logs -f'
   ```

3. **Test the application:**
   - Visit: `http://YOUR_SERVER_IP`
   - Or if using ALB: `https://your-alb-url`
   - Should see login page

## Step 9: Create Admin User

After deployment, create the first admin user:

```bash
ssh ubuntu@YOUR_SERVER_IP

cd /opt/borehole
docker-compose -f docker-compose.prod.yml exec backend python3 /app/scripts/create_admin_user.py admin YOUR_PASSWORD
```

Use the password from Step 3 (database secret).

## Step 10: Test Application

1. Visit: `http://YOUR_SERVER_IP`
2. Login with admin credentials
3. Verify map loads
4. Check backend API: `http://YOUR_SERVER_IP/api/health`

## Ongoing Deployments

For future deployments:

```bash
# Push code changes
git push origin master

# Wait for GitHub Actions to build (~5-10 minutes)

# Deploy
./scripts/deploy-prod.sh YOUR_SERVER_IP ubuntu
```

## Troubleshooting

### Images not found
- Check GitHub Actions completed successfully
- Verify ECR repositories exist
- Ensure images were pushed: `aws ecr list-images --repository-name borehole-frontend --region us-east-2`

### Cannot SSH to server
- Verify security group allows SSH from your IP
- Check server is running
- Verify SSH key is configured

### Services won't start
- Check logs: `docker-compose -f docker-compose.prod.yml logs`
- Verify secrets were fetched: `cat /opt/borehole/.env.prod`
- Check disk space: `df -h`

### Database connection issues
- Verify MySQL container is running: `docker-compose ps mysql`
- Check database logs: `docker-compose logs mysql`
- Test connection: `docker-compose exec backend python3 -c "from src.api.database import db; db.connect()"`

### Permission issues
- Verify user is in docker group: `groups`
- May need to log out/in after adding to docker group

## Maintenance

### Backup Database

```bash
ssh ubuntu@YOUR_SERVER_IP
cd /opt/borehole

# Backup MySQL volume
docker-compose exec mysql mysqldump -u borehole_user -p borehole_db > backup_$(date +%Y%m%d).sql
```

### Update Application

```bash
# On local machine
git push origin master
# Wait for build...
./scripts/deploy-prod.sh YOUR_SERVER_IP ubuntu
```

### View Logs

```bash
ssh ubuntu@YOUR_SERVER_IP
cd /opt/borehole
docker-compose -f docker-compose.prod.yml logs -f [service-name]
```

### Restart Services

```bash
ssh ubuntu@YOUR_SERVER_IP
cd /opt/borehole
docker-compose -f docker-compose.prod.yml restart
```

## Security Notes

- `.env.prod` contains sensitive data - never commit to git
- Use IAM roles instead of AWS credentials when possible
- Regularly rotate secrets in AWS Secrets Manager
- Enable automatic security updates on EC2 instance
- Consider using AWS Systems Manager Session Manager instead of SSH keys

---

**Support:** See `README.md` for detailed architecture and troubleshooting.

