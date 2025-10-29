# Borehole Analysis Application

Modern web application for processing Excel gradation reports from Box and displaying interactive borehole maps with real-time updates.

## Features

- **React Frontend**: Interactive Mapbox map with login authentication
- **Flask REST API**: JWT-based authentication and data endpoints
- **MySQL Database**: Secure user credential storage
- **Automated Pipeline**: Continuously processes Box data every 10 minutes
- **Interactive Map**: Real-time borehole visualization with depth intervals and FM values
- **Multi-Mine Support**: Handles multiple mine areas with separate outputs
- **Audit Trail**: Generates CSV audit logs for all processed data
- **Dockerized**: Full Docker Compose setup for easy deployment

## Architecture

```
┌─────────┐     ┌──────────┐     ┌────────┐     ┌─────────┐
│  Box    │────▶│ Pipeline │────▶│  KMZ   │────▶│ Backend │
│         │     │ Service  │     │ Files  │     │   API   │
└─────────┘     └──────────┘     └────────┘     └─────────┘
                                                     │
                     ┌──────────────────────────────┼──────────────┐
                     │                              │              │
                ┌────▼────┐                   ┌────▼────┐    ┌────▼────┐
                │ Frontend│                   │   MySQL │    │  Nginx  │
                │  React  │                   │ Database│    │  Proxy  │
                └─────────┘                   └─────────┘    └─────────┘
```

### Services

1. **MySQL Database** (`mysql`)
   - Stores user credentials (username, hashed password)
   - Initialized with schema from `database/init.sql`
   - Persistent volume for data storage
   - Port: 3306

2. **Backend API** (`backend`)
   - Flask REST API on port 5000 (exposed as 5001)
   - JWT-based authentication
   - Endpoints:
     - `POST /api/auth/login` - User login
     - `GET /api/auth/verify` - Verify token
     - `GET /api/auth/health` - Health check
     - `GET /api/geojson` - Get borehole data (requires auth)
     - `GET /api/status` - Pipeline status (requires auth)

3. **Pipeline Service** (`pipeline`)
   - Background service that continuously processes Box data
   - Runs every 10 minutes by default
   - Generates KMZ files in `/app/output`
   - Writes to shared volume accessible by backend

4. **Frontend** (`frontend`)
   - React SPA built with Vite
   - Served by nginx on port 80 (inside container)
   - Mapbox integration for map visualization
   - Accessible on port 3000 (development) or 80 (via nginx proxy)

5. **Nginx** (`nginx`)
   - Reverse proxy on port 80
   - Serves React frontend at `/`
   - Proxies API requests to backend at `/api/*`

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Mapbox account (free tier works) - https://account.mapbox.com/access-tokens/

### 1. Configure Environment

   ```bash
# Copy example environment file
cp .env.example .env

# Edit .env and set:
# - MYSQL_PASSWORD (use a strong password)
# - JWT_SECRET_KEY (generate with: python3 -c "import secrets; print(secrets.token_urlsafe(32))")
# - MAPBOX_TOKEN (your Mapbox access token)
```

### 2. Build and Start Services

```bash
# Build all services
docker-compose up --build

# Or use the run script
./run.sh start
```

This starts:
- **MySQL** on port 3306
- **Backend API** on port 5001 (5000 inside container)
- **Frontend** on port 3000
- **Nginx Proxy** on port 80 (main entry point)
- **Pipeline** service (background processing)

### 3. Create Admin User

In a new terminal, after services are running:

```bash
docker-compose exec backend python3 scripts/create_admin_user.py admin yourpassword
```

### 4. Access Application

Open your browser: **http://localhost:80**

Login with:
- Username: `admin`
- Password: (the one you set in step 3)

## Development

### Frontend (React)

```bash
cd frontend
npm install
npm run dev
```

Access at: http://localhost:3000

### Backend API

```bash
# Set environment variables
export MYSQL_HOST=localhost
export MYSQL_USER=borehole_user
export MYSQL_PASSWORD=borehole_password
export MYSQL_DATABASE=borehole_db
export JWT_SECRET_KEY=dev-secret-key

# Run API
python3 -m src.api.app
```

### Pipeline Service

```bash
# Run pipeline once
docker-compose run --rm pipeline python3 -m src.main --once

# Use local test data
USE_LOCAL_DATA=true docker-compose run --rm pipeline python3 -m src.main --once
```

## Configuration

### Pipeline Configuration (`config/config.yaml`)

- Mine area settings
- Box folder IDs (use placeholders in public repos)
- Output file templates
- Validation settings

### Box Integration

1. Place `box_config.json` in `secrets/` directory
2. Configure Box folder IDs in `config/config.yaml`
3. Set `USE_LOCAL_DATA=false` in `.env` (or keep `true` for local testing)

### Mapbox Token

Get free token at: https://account.mapbox.com/access-tokens/

Set in `.env`:
```bash
MAPBOX_TOKEN=pk.your_token_here
```

## Project Structure

```
├── frontend/              # React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── Login.jsx
│   │   │   └── Map.jsx
│   │   ├── App.jsx
│   │   └── main.jsx
│   └── Dockerfile
├── src/
│   ├── api/              # Backend REST API
│   │   ├── app.py        # Flask app
│   │   ├── auth.py       # Authentication endpoints
│   │   ├── data.py       # Data endpoints
│   │   ├── database.py   # MySQL connection
│   │   └── middleware.py # JWT middleware
│   └── main.py          # Pipeline service
├── database/
│   └── init.sql         # MySQL schema
├── config/              # Pipeline configuration
│   └── config.yaml
├── scripts/             # Utility scripts
│   ├── create_admin_user.py
│   └── create_stub_data.py
├── secrets/             # Credentials (NOT committed)
│   └── box_config.json
└── docker-compose.yml
```

## API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `GET /api/auth/verify` - Verify JWT token
- `GET /api/auth/health` - Health check

### Data (requires authentication)
- `GET /api/geojson` - Get borehole GeoJSON data
- `GET /api/status` - Pipeline status

All data endpoints require JWT token in `Authorization: Bearer <token>` header.

## Security

### Sensitive Information

This project contains sensitive information that should **NEVER** be committed to version control:

**Protected Files (.gitignore):**
- `.env` - Contains all secrets (passwords, tokens, API keys)
- `secrets/*` - Box API credentials and other secrets (all files ignored)
- `logs/` - Audit logs with potentially sensitive data
- `output/` - Generated KMZ files

**Environment Variables (.env):**
- `JWT_SECRET_KEY` - Used to sign authentication tokens
- `MYSQL_PASSWORD` - Database password
- `MYSQL_ROOT_PASSWORD` - MySQL root password
- `MAPBOX_TOKEN` - Mapbox API token
- `BOX_AS_USER_ID` - Box service account ID
- `BOX_CONFIG` - Path to Box API credentials file

**Configuration Files:**
- `config/config.yaml` - Contains Box folder IDs (business-sensitive)
  - Use placeholders for public repository
  - Store actual IDs in local `.env` if needed

### Security Best Practices

1. **Never commit `.env` file** - Always use `.env.example` with placeholders
2. **Never commit files in `secrets/`** - All files are automatically ignored
3. **Rotate secrets periodically** - Change passwords and JWT keys in production
4. **Use strong passwords** - Generate secure random strings for production
5. **Review before committing** - Check for hardcoded secrets in code

### Before First Commit

```bash
# Ensure .env is not tracked
git rm --cached .env

# Verify .env.example has placeholders only
grep -v "^#" .env.example | grep -E "(password|secret|token)"

# Check for hardcoded secrets
grep -r "password\|secret\|token" --include="*.py" --include="*.js" --include="*.jsx" src/ frontend/src/
```

## Troubleshooting

### Services won't start
```bash
docker-compose logs
```

### Can't login
```bash
# Check backend logs
docker-compose logs backend

# Verify database connection
docker-compose exec mysql mysql -u borehole_user -p borehole_db

# Check if user exists
docker-compose exec backend python3 -c "from src.api.database import db; db.connect(); print(db.get_user_by_username('admin'))"
```

### No map data
```bash
# Check pipeline logs
docker-compose logs pipeline

# Verify KMZ generation
ls -la output/

# Check if pipeline processed data
docker-compose logs pipeline | grep "KMZ generated"
```

### Frontend issues
```bash
# Check frontend logs
docker-compose logs frontend

# Rebuild frontend
docker-compose build frontend && docker-compose up -d frontend
```

### Port conflicts
```bash
# Backend port conflict (default 5000)
# Already configured to use 5001 externally

# If MySQL port conflicts, change in docker-compose.yml
# If nginx port conflicts, change "80:80" to "8080:80"
```

### Mapbox token not working
```bash
# Verify token is injected
docker-compose exec frontend cat /usr/share/nginx/html/index.html | grep MAPBOX_TOKEN

# Rebuild frontend with new token
docker-compose build frontend && docker-compose up -d frontend
```

## Production Deployment

### Server Setup

See `deploy/setup_server.sh` for automated server setup including:
- Docker and Docker Compose installation
- Directory structure creation
- Systemd service configuration

### Environment Variables

For production, set these securely:
- Use environment variables or secret management services
- Never hardcode secrets in source code
- Use different secrets for production vs development
- Enable HTTPS/TLS for all connections

### Database

MySQL data persists in Docker volume `mysql_data`. Backup regularly:
```bash
docker-compose exec mysql mysqldump -u borehole_user -p borehole_db > backup.sql
```

### Updates

```bash
# Pull latest code
git pull

# Rebuild and restart services
docker-compose build
docker-compose up -d

# Check logs
docker-compose logs -f
```

## Utility Scripts

- `scripts/create_admin_user.py <username> <password>` - Create new user
- `scripts/create_stub_data.py` - Generate test Excel files
- `scripts/diagnose_box_permissions.py` - Debug Box API issues
- `scripts/test_box_connection.py` - Test Box API connection

## License

[Your License Here]

### Server Access

- **SSM Session Manager (preferred, no SSH keys):**
  ```bash
  aws ssm start-session \
    --target i-03169bf6f17bc4a23 \
    --region us-east-2 \
    --profile hcmining-prod
  ```
  Ensure the instance role allows `ssm:StartSession` and `ssm:DescribeInstanceInformation`; Ubuntu 22.04 images ship with the SSM agent enabled by default.

- **SSH (if enabled):**
  1. Confirm security group `sg-0e46e94bb982b73bd` allows SSH (port 22) from your current IP.
  2. Connect (add `-i /path/to/key.pem` if your key is not already in the SSH agent):
     ```bash
     ssh ubuntu@18.216.19.153
     ```
  3. On login, change to the app directory and use the system docker-compose binary for all commands:
     ```bash
     cd /opt/borehole
     sudo DOCKER_CONFIG=/root/.docker /usr/local/bin/docker-compose -f docker-compose.prod.yml ps
     ```
     Prefix other compose operations the same way (e.g. `logs -f`, `exec backend`, `restart`).
