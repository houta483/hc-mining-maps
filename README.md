# Borehole Analysis Application

End-to-end system that turns Box-hosted gradation spreadsheets into KMZ/GeoJSON outputs and presents them through a secure, Mapbox-powered web map. Everything runs through Docker Compose both locally and on a single EC2 server.

## Table of Contents

- [Borehole Analysis Application](#borehole-analysis-application)
  - [Table of Contents](#table-of-contents)
  - [Project Overview](#project-overview)
  - [Architecture](#architecture)
  - [Repository Layout](#repository-layout)
  - [Local Development](#local-development)
    - [Prerequisites](#prerequisites)
    - [Initial Setup](#initial-setup)
    - [Daily Usage](#daily-usage)
    - [Optional Tasks](#optional-tasks)
  - [Production Deployment](#production-deployment)
    - [Quick Reference](#quick-reference)
    - [One-Time Setup](#one-time-setup)
    - [Deploying Updates](#deploying-updates)
    - [Server Access](#server-access)
  - [Operations \& Maintenance](#operations--maintenance)
  - [Security Practices](#security-practices)
  - [Troubleshooting](#troubleshooting)
  - [Support](#support)

## Project Overview

- React frontend with Mapbox visualisation and JWT-authenticated sessions
- Flask API serving authentication, GeoJSON data, and pipeline status
- MySQL database container for user persistence
- Pipeline container that polls Box every ~10 minutes, producing KMZ and audit CSV files
- Docker Compose orchestrates all services locally and on production EC2

## Architecture

```
┌─────────────┐      ┌──────────────┐       ┌─────────────┐
│    Box      │ ───▶ │   Pipeline   │ ───▶  │   Outputs   │
│ (Excel CSV) │      │ (src/main.py)│       │ KMZ / Audit │
└─────────────┘      └──────┬───────┘       └──────┬──────┘
                             │                     │
                             ▼                     │
                     ┌───────────────┐             │
                     │   Backend     │ ◀───────────┘
                     │  (Flask API)  │
                     └──────┬────────┘
                            │
                 ┌──────────▼──────────┐
                 │      Nginx          │
                 │ (reverse proxy)     │
                 └──────────┬──────────┘
                            │
                     ┌──────▼──────┐
                     │  Frontend   │
                     │  (React)    │
                     └─────────────┘
```

**Core services**
- `mysql`: MySQL 8.0, stores users; initialised via `database/init.sql`
- `backend`: Flask API (`src/api`), exposes auth and GeoJSON endpoints
- `pipeline`: long-running job (`src/main.py`) that fetches Box files and produces KMZ/audit data
- `frontend`: React SPA bundled with Vite, served by nginx
- `nginx`: reverse proxy front-door, terminates HTTP, serves static assets, proxies `/api/*`

More detail is inside `docker-compose.yml` and `docker-compose.prod.yml`.

## Repository Layout

```
├── config/                 # Pipeline configuration (Box folders, retention, etc.)
│   └── config.yaml
├── database/
│   └── init.sql            # MySQL schema bootstrap
├── deploy/
│   └── nginx.conf          # Nginx vhost for prod compose
├── docker-compose.yml      # Local stack
├── docker-compose.prod.yml # Prod stack (single server)
├── frontend/               # React application
│   ├── Dockerfile
│   └── src/
├── scripts/                # Helper scripts
│   ├── deploy-prod.sh      # One-command prod deploy to the EC2 host
│   ├── fetch-secrets.sh    # Optional helper if you store secrets in AWS
│   ├── create_admin_user.py
│   ├── run_initialization.sh
│   └── ...
├── src/                    # Python backend + pipeline code
│   ├── api/
│   └── main.py
├── tests/                  # Pytest suite for parsing utilities
└── run.sh                  # Convenience wrapper around docker compose (local)
```

## Local Development

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Python 3.11+ (already bundled in containers but useful for scripts)
- Node 18+ if you want to run the React dev server outside Docker
- Mapbox account (free tier) to generate an access token

### Initial Setup

1. **Clone and install tooling**
   ```bash
   git clone https://github.com/houta483/hc-mining-maps.git
   cd hc-mining-maps
   ```

2. **Create environment file**
   ```bash
   cp .env.example .env
   ```
   Fill in at least:
   - `MYSQL_PASSWORD` – strong local password
   - `JWT_SECRET_KEY` – `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `MAPBOX_TOKEN` – from https://account.mapbox.com/access-tokens/

3. **Box configuration (optional)**
   - Place the Box app config at `secrets/box_config.json` (ignored by git)
   - Update `config/config.yaml` with your Box folder ID if you have it
   - Leave `parent_folder_id` as a placeholder if running locally without Box

4. **Install frontend dependencies (optional)**
   ```bash
   cd frontend
   npm install
   cd ..
   ```

### Daily Usage

- **Start the full stack**
  ```bash
  ./run.sh start      # builds containers on first run
  ```
  Services exposed locally:
  - Frontend via nginx: `http://localhost`
  - Backend API: `http://localhost:5001` (proxied through nginx)
  - MySQL: `localhost:3306`

- **Stop or reset**
  ```bash
  ./run.sh stop       # stop containers but keep volumes
  ./run.sh clean      # stop containers AND remove volumes (resets MySQL)
  ```

- **View logs**
  ```bash
  ./run.sh logs       # aggregated logs
  docker compose logs backend
  docker compose logs pipeline
  ```

- **Create an admin user** (after stack is up)
  ```bash
  docker compose exec backend \
      python3 /app/scripts/create_admin_user.py asdf asdf
  ```

- **Visit the app**
  - Browser: `http://localhost`
  - Login with the credentials you just created

### Optional Tasks

- **Run pipeline once instead of continuously**
  ```bash
  docker compose run --rm pipeline python3 -m src.main --once
  ```

- **Use bundled test data instead of Box**
  ```bash
  USE_LOCAL_DATA=true ./run.sh start
  # or modify .env and restart the pipeline container
  ```

- **Execute tests**
  ```bash
  pytest
  ```

- **Debug Box connectivity**
  ```bash
  docker compose exec pipeline python3 /app/scripts/test_box_connection.py
  ```

### Drone Imagery Overlay Workflow

The app now supports uploading, aligning, and storing high-resolution drone imagery entirely in the UI. The modal wizard guides you through three stages:

1. **Select Image**
   - Click `Upload New Drone Overlay` in the sidebar and choose a PNG, JPEG, or WebP image (≤ 200 MB).
   - The filename pre-fills the overlay name but you can change it later.

2. **Align on Map**
   - Click `Open Alignment Mode` to display the image over the map.
   - Drag the **center handle** to reposition the overlay.
   - Drag the **corner handle** outward/inward to scale uniformly.
   - Use the rotation slider in the alignment HUD if the imagery needs to twist to match the basemap.
   - When the edges line up, click `Done aligning`.

3. **Review & Submit**
   - Adjust the name, capture date, default opacity, and whether the overlay starts visible.
   - Click `Upload Overlay`. The backend georeferences the image with GDAL and publishes it immediately when finished.

You can always reopen alignment (via `Adjust alignment`) before uploading if you want to tweak the fit again. The most recent upload becomes the active overlay and is available via `/api/overlay/latest`.

## Production Deployment

A single Ubuntu EC2 instance runs the full Docker Compose stack (MySQL, backend, pipeline, frontend, nginx). Images build on the host—no ECR, ECS, or extra infrastructure required.

### Quick Reference

| Item | Value |
|------|-------|
| Region | `us-east-2` |
| Instance ID | `i-03169bf6f17bc4a23` |
| Public IP | `18.216.19.153` |
| App Directory | `/opt/borehole` |
| Frontend URL | `http://18.216.19.153` |
| Backend health | `http://18.216.19.153/api/health` |

### One-Time Setup

1. **Provision the server**
   - Ubuntu 22.04 LTS (t3.small or larger)
   - Security group open on ports 22/80 (443 optional until TLS is added)
   - (Optional) Attach an IAM role if you plan to use AWS CLI from the box

2. **Install Docker + prerequisites**
   ```bash
   scp scripts/setup-server.sh ubuntu@18.216.19.153:/tmp/
   ssh ubuntu@18.216.19.153 'bash /tmp/setup-server.sh'
   ```
   The script installs Docker, Docker Compose, AWS CLI, and prepares `/opt/borehole` with the expected subdirectories.

3. **Create production environment file**
   - Copy `.env.example` → `.env.prod`
   - Set MySQL credentials, JWT secret, Mapbox token, Box folder IDs, refresh settings, etc.
   - Keep `.env.prod` out of git; the deploy script uploads it securely.

4. **Provide Box credentials**
   - Place `secrets/box_config.json` locally (ignored by git)
   - Deployment copies it to `/opt/borehole/secrets/box_config.json`

### Deploying Updates

1. Ensure your working tree has the changes you want (committed or not).

2. Run the helper:
   ```bash
   ./scripts/manage.sh prod
   # or: ./scripts/deploy-prod.sh 18.216.19.153 ubuntu
   ```
   Under the hood it:
   - rsyncs the repo to `/opt/borehole` (excluding `logs/` and `output/`)
   - uploads `.env.prod` and `secrets/box_config.json` if present locally
   - symlinks `.env` → `.env.prod`
   - executes `docker compose -f docker-compose.prod.yml up -d --build`
   - prints `docker compose ps` for a quick status check

3. Verify the stack:
   ```bash
   ssh ubuntu@18.216.19.153
   cd /opt/borehole
   docker compose -f docker-compose.prod.yml ps
   docker compose -f docker-compose.prod.yml logs -f pipeline
   ```

### Server Access

- **SSH** (primary)
  ```bash
  ssh ubuntu@18.216.19.153  # add -i /path/to/key.pem if required
  cd /opt/borehole
  docker compose -f docker-compose.prod.yml ps
  ```

- **AWS SSM (optional)**
  ```bash
  aws ssm start-session \
    --target i-03169bf6f17bc4a23 \
    --region us-east-2
  ```

## Operations & Maintenance

- **Log locations**
  - Application logs: `/opt/borehole/logs/`
  - Docker logs: `docker compose -f docker-compose.prod.yml logs -f <service>`
  - Pipeline cleans up audit CSVs older than the retention in `config/config.yaml`

- **Outputs**
  - KMZ, GeoJSON, audit CSV: `/opt/borehole/output`

- **Database backups**
  ```bash
  docker compose -f docker-compose.prod.yml exec mysql \
    mysqldump -u borehole_user -p${MYSQL_PASSWORD} borehole_db > backup_$(date +%Y%m%d).sql
  ```

- **Restart services**
  ```bash
  docker compose -f docker-compose.prod.yml restart
  ```

- **Stop everything**
  ```bash
  docker compose -f docker-compose.prod.yml down
  ```

- **Switch pipeline to local test data**
  Edit `/opt/borehole/.env.prod` and set `USE_LOCAL_DATA=true`, then restart the pipeline service.

## Security Practices

- `.env`, `.env.prod`, files under `secrets/`, `logs/`, and `output/` are ignored by git—keep it that way.
- Store production secrets in `.env.prod` and `secrets/box_config.json` securely; rotate credentials periodically.
- Use unique credentials for development vs production (different database passwords, JWT keys, Mapbox tokens).
- Limit access to the EC2 security group (lock SSH to trusted IP ranges; consider adding TLS/ACM for HTTPS).
- Regularly review Box collaboration permissions for the service account.
- When in doubt, run `git status` before committing to ensure no sensitive files are staged.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| `Access denied for user 'borehole_user'` | MySQL volume seeded with old password | Remove the volume (`./run.sh clean` locally or `docker volume rm` in prod) and restart |
| Frontend loads but map is blank | Missing/invalid `MAPBOX_TOKEN` | Update `.env` locally or `.env.prod` on the server, redeploy |
| Pipeline container keeps restarting | Missing Box config or env vars | Ensure `.env.prod` has Box IDs and `secrets/box_config.json` exists, then redeploy |
| Cannot SSH into EC2 | Security group or key issue | Check that SG allows your IP on port 22 and correct key is used |
| Deploy script errors: `Missing .env.prod` | `.env.prod` not present locally or on server | Create/populate `.env.prod`, re-run deploy |
| Local login fails | User not created or wrong password | `docker compose exec backend python3 /app/scripts/create_admin_user.py admin <pw>` |
| Box fetch fails with 403 | Service account not added to Box folder | Invite the Box app user as a collaborator and re-run pipeline |

## Support

Need a manual checklist or deeper AWS notes? See the scripts in `scripts/`—each is heavily commented. If anything drifts from this README (new services, ports, secrets), update this file as part of your change.

Happy drilling!
