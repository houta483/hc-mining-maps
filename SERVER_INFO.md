# Server Deployment Information

## EC2 Instance

**Instance Details:**
- **Instance ID:** `i-03169bf6f17bc4a23`
- **Public IP:** `18.216.19.153`
- **Public DNS:** `ec2-18-216-19-153.us-east-2.compute.amazonaws.com`
- **Instance Type:** `t3.small`
- **AMI:** Ubuntu 22.04 LTS
- **Region:** `us-east-2`
- **Status:** Running

**SSH Access:**
```bash
ssh -i ~/.ssh/hc-mining-bastion-admin.pem ubuntu@18.216.19.153
```

Or if the key is in your SSH agent:
```bash
ssh ubuntu@18.216.19.153
```

## Security Group

- **Security Group ID:** `sg-0e46e94bb982b73bd`
- **Name:** `borehole-app-sg`
- **Rules:**
  - SSH (22): 0.0.0.0/0
  - HTTP (80): 0.0.0.0/0
  - HTTPS (443): 0.0.0.0/0

## Next Steps

1. **Wait for SSH** (~60 seconds after launch)
2. **Set up server:**
   ```bash
   scp scripts/setup-server.sh ubuntu@18.216.19.153:/tmp/
   ssh ubuntu@18.216.19.153 'sudo bash /tmp/setup-server.sh'
   ```

3. **Deploy application:**
   ```bash
   ./scripts/deploy-prod.sh 18.216.19.153 ubuntu
   ```

## Application URL

Once deployed:
- **Frontend:** `http://18.216.19.153`
- **Backend API:** `http://18.216.19.153/api`

## Tags

- `Name`: borehole-app-server
- `Project`: borehole-analysis
- `Service`: borehole-app

