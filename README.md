# Borehole Analysis Application

End-to-end system for fetching gradation spreadsheets from Box, processing them into KMZ/GeoJSON, and exposing them through a secure web UI. The stack is fully containerised for easy local development and single-server production deployment.

<div align="center">

```
┌───────────────┐     ┌───────────────┐     ┌────────────┐
│     Box       │ ───▶│   Pipeline    │────▶│   Outputs   │
│ (Excel files) │     │  (Scheduled)  │     │ (KMZ/Audit)│
└───────────────┘     └──────┬────────┘     └────┬───────┘
                              │                  │
                              ▼                  │
                      ┌──────────────┐           │
                      │   Backend    │ ◀─────────┘
                      │   (Flask)    │
                      └──────┬───────┘
                             │
                ┌────────────▼────────────┐
                │   Nginx Reverse Proxy   │
                └────────────┬────────────┘
                             │
                      ┌──────▼──────┐
                      │  Frontend   │
                      │  (React)    │
                      └─────────────┘
```

</div>

All services are orchestrated via Docker Compose locally and on production EC2.

---

## Table of Contents

1. [Repository Structure](#repository-structure)
2. [Service Overview](#service-overview)
3. [Local Development](#local-development)
   - [Prerequisites](#prerequisites)
   - [Initial Setup](#initial-setup)
   - [Running the Stack](#running-the-stack)
   - [Box Integration Locally](#box-integration-locally)
   - [Useful Commands](#useful-commands)
4. [Production Deployment](#production-deployment)
   - [First-Time Setup Checklist](#first-time-setup-checklist)
   - [Secrets & AWS Prerequisites](#secrets--aws-prerequisites)
   - [Deploying Updates](#deploying-updates)
   - [Server Access](#server-access)
   - [Prod Quick Reference](#prod-quick-reference)
5. [Operations & Maintenance](#operations--maintenance)
   - [Command Cheat Sheet](#command-cheat-sheet)
6. [Security Guidance](#security-guidance)
7. [Troubleshooting](#troubleshooting)

---

## Repository Structure

```
.
├── config/                 # Pipeline configuration
│   └── config.yaml
├── database/
│   └── init.sql            # MySQL schema
├── deploy/
│   └── nginx.conf          # Nginx reverse proxy
├── frontend/               # React web app
│   ├── Dockerfile
│   └── src/...
├── scripts/
│   ├── create_admin_user.py
│   ├── fetch-secrets.sh
│   ├── deploy-prod.sh
│   ├── run_initialization.sh
│   └── ...
├── src/
│   ├── api/                # Flask backend
│   └── main.py             # Pipeline entrypoint
├── docker-compose.yml      # Local stack
├── docker-compose.prod.yml # Production stack
├── README.md               # This document
└── run.sh                  # Helper for local docker-compose
```

---

## Service Overview

| Service  | Description | Ports | Notes |
|----------|-------------|-------|-------|
| `mysql` | MySQL 8.0 database storing user credentials | 3306 | Data persisted in Docker volume `borehole_analysis_app_mysql_data` |
| `backend` | Flask API providing authentication & GeoJSON API | Exposed as 5001 (container 5000) | Uses JWT, reads processed KMZ/Audit files |
| `pipeline` | Background processor downloading from Box and producing KMZ, audit & GeoJSON | n/a | Runs continuously (or once via `--once`) |
| `frontend` | React SPA bundled by Vite & served by nginx | 3000 (or 80 through proxy) | Uses Mapbox token for map visualisation |
| `nginx` | Reverse proxy entrypoint | 80 (and 443 in prod compose) | Serves frontend & proxies `/api/*` |

---

## Local Development

### Prerequisites

- Docker Desktop (or Docker Engine + Compose)  
- Python 3.11+ (for optional direct script execution)  
- Node 18+ (only if developing the React app outside Docker)  
- Mapbox account (free tier) to obtain an access token

### Initial Setup

1. **Fetch secrets (optional but recommended)**
   ```bash
   AWS_PROFILE=hcmining-prod AWS_REGION=us-east-2 ./scripts/fetch-secrets.sh
   cp .env.prod .env  # local override; edit if needed
   ```
   If you do not have AWS access yet, manually create a `.env` using `.env.example` as reference.

2. **Ensure Box config is present**
   - Download the authorised Box app config (JSON)  
   - Place it at `secrets/box_config.json` (kept out of git).

3. **Update pipeline configuration** (`config/config.yaml`)
   ```yaml
   parent_folder_id: "<YOUR_BOX_FOLDER_ID>"
   s3_bucket: "hc-mining-maps"
   cloudfront_distribution_id: "<CF_DIST_ID>"
   public_url_template: "https://<cf-domain>/<filename>"
   ```
   For local-only testing you can leave S3/CloudFront placeholders; they’re only used when publishing to S3.

4. **Install JS dependencies (optional)**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

### Running the Stack

The `run.sh` helper ensures directories exist and uses docker-compose under the hood.

```bash
./run.sh start    # build & launch all containers (first run will populate MySQL)
./run.sh stop     # stop containers (retain volumes)
./run.sh clean    # stop & remove containers + volumes (useful when resetting MySQL)
./run.sh logs     # follow logs for all services
```

**Note on passwords:** the first time MySQL starts it uses the credentials from `.env`. If you later change them, run `./run.sh clean` to rebuild the database volume.

### Creating Users Locally

After the containers are running:

```bash
# create an admin user (username/password)
docker-compose exec backend python3 /app/scripts/create_admin_user.py asdf asdf
```

Visit `http://localhost` and log in with those credentials.

### Box Integration Locally

1. Ensure `USE_LOCAL_DATA=false` in `.env` (the default after running `fetch-secrets.sh`).
2. Confirm `secrets/box_config.json` contains the full Box credentials (clientID, clientSecret, enterpriseID & appAuth if using JWT).
3. Restart the pipeline if needed:
   ```bash
   docker-compose restart pipeline
   docker-compose logs -f pipeline
   ```
   You should see logs such as “Authenticated as user …” and file discovery.

### Useful Commands

```bash
./run.sh status                          # docker-compose ps + last logs
./run.sh shell                           # open shell into backend container
USE_LOCAL_DATA=true ./run.sh start       # run pipeline against local test_data
./run.sh restart                         # quick bounce of all containers

# Run pipeline once (from host)
docker-compose run --rm pipeline python3 -m src.main --once

# Tail specific service logs
docker-compose logs -f backend
```

---

## Production Deployment

Production uses the same containers orchestrated by `docker-compose.prod.yml` on a single EC2 instance.

### First-Time Setup Checklist

1. **Container registry** – `infra/ecr` Terraform (`terraform init && terraform apply`).
2. **GitHub secrets** – add `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `MAPBOX_TOKEN`.
3. **AWS Secrets Manager** – create: `prod/borehole/db`, `prod/borehole/jwt`, `prod/borehole/mapbox`, `prod/borehole/box` (see below for payload examples).
4. **EC2 instance** – Ubuntu 22.04+, t3.small+, security group allowing 22/80/443.
5. **Install Docker & awscli on server** – run `scripts/setup-server.sh` or equivalent.
6. **Ensure IAM role or AWS credentials** with access to ECR + Secrets Manager.
7. **Push code to master** – wait for GitHub Actions to build & push images (`frontend`, `backend`, `pipeline`).

### Secrets & AWS Prerequisites

Create Secrets Manager entries (JSON shown below). All values are strings.

- `prod/borehole/db`
  ```json
  {
    "host": "mysql",
    "port": "3306",
    "database": "borehole_db",
    "username": "borehole_user",
    "password": "<strong password>"
  }
  ```
- `prod/borehole/jwt`
  ```json
  { "secret_key": "<long random string>" }
  ```
- `prod/borehole/mapbox`
  ```json
  { "token": "pk.xxx" }
  ```
- `prod/borehole/box` – contents of your Box app config JSON (entire file).

### Deploying Updates

Once the one-time setup is complete, deployments are:

```bash
# 1. Push code (triggers GitHub Actions build)
git push origin master

# 2. Deploy to server after build finishes (~5–10 minutes)
./scripts/deploy-prod.sh <SERVER_IP> ubuntu
```

The deploy script waits for images, copies config to the server, pulls from ECR, fetches secrets, and runs `docker-compose -f docker-compose.prod.yml up -d`.

After a deploy, create/verify the admin user if needed:

```bash
ssh ubuntu@<SERVER_IP>
cd /opt/borehole
sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml exec backend python3 /app/scripts/create_admin_user.py admin <password>
```

### Server Access

- **SSM Session Manager (preferred, no SSH keys):**
  ```bash
  aws ssm start-session \
    --target i-03169bf6f17bc4a23 \
    --region us-east-2 \
    --profile hcmining-prod
  ```
- **SSH (if enabled):**
  ```bash
  ssh ubuntu@18.216.19.153
  ```

### Prod Quick Reference

| Item | Value |
|------|-------|
| Instance ID | `i-03169bf6f17bc4a23` |
| Public IP | `18.216.19.153` |
| Region | `us-east-2` |
| Security group | `sg-0e46e94bb982b73bd` (80/443/22 open) |
| App root | `/opt/borehole` |
| Entry URL | `http://18.216.19.153` |
| Backend health | `http://18.216.19.153/api/health` |

Common commands on the server:
```bash
cd /opt/borehole
sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml ps
sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml logs -f
sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml restart
```

---

## Operations & Maintenance

- **Logs**: `docker-compose logs` or service-specific logs under `/opt/borehole/logs`.
- **Outputs**: KMZ & audit CSVs under `/opt/borehole/output`.
- **Database backups**:
  ```bash
  sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml exec mysql \
    mysqldump -u borehole_user -p${MYSQL_PASSWORD} borehole_db > backup_$(date +%Y%m%d).sql
  ```
- **Rolling restart**:
  ```bash
  sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml restart
  ```

### Command Cheat Sheet

| Task | Command |
|------|---------|
| Create admin user | `docker compose -f docker-compose.prod.yml exec backend python3 /app/scripts/create_admin_user.py admin PASSWORD` |
| Test DB connection | `docker compose -f docker-compose.prod.yml exec backend python3 -c "from src.api.database import Database; db = Database(); db.connect(); print('OK')"` |
| Test Box connection | `docker compose -f docker-compose.prod.yml exec pipeline python3 /app/scripts/test_box_connection.py` |
| Tail pipeline logs | `docker compose -f docker-compose.prod.yml logs -f pipeline` |
| Run pipeline once | `docker compose -f docker-compose.prod.yml exec pipeline python3 -m src.main --once` |
| Drop into backend shell | `docker compose -f docker-compose.prod.yml exec backend /bin/bash` |
| View container status | `docker compose -f docker-compose.prod.yml ps` |

(Substitute `docker compose` with `sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose` on the production server.)

---

## Security Guidance

- Never commit `.env`, files under `secrets/`, or generated outputs.  
- Production secrets belong in AWS Secrets Manager; `.env` is for local development only.  
- Rotate JWT secrets and database passwords periodically.  
- For production, front the EC2 instance with TLS (load balancer or nginx cert).  
- Prefer IAM roles on EC2 instead of static AWS keys.  
- Audit Box app scopes and ensure only the required folders are shared with the service account.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `Access denied for user 'borehole_user'` | MySQL volume created with old password | `./run.sh clean` (local) or remove volume on server, then restart |
| `Invalid token: Signature verification failed` | Frontend using stale JWT | Log out/in (clears localStorage token) |
| Pipeline logs `--continuous` error | Wrong command; ensure pipeline command is `python3 -m src.main` | Update compose file and restart |
| Box 403 / empty results | Service account not collaborator or scopes missing | Invite service account to Box folder, ensure app authorised |
| Mapbox map blank | Token missing/invalid | Update `.env`, rebuild frontend container |
| Prod deploy script hangs on secrets | IAM role/credentials missing Secrets Manager access | Attach role or configure AWS credentials |
| `docker-compose` not found on server | Install plugin (`sudo apt install docker-compose-plugin`) or use standalone binary | Follow setup script |

---

If you follow this README from scratch, you can stand up the full stack locally, configure Box integration, and promote the same containers into production.
