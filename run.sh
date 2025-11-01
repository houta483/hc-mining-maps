#!/bin/bash
# Borehole Analysis Pipeline - Run Script
# Runs pipeline with Mapbox web server

set -e

ENV_FILE_PATH="${ENV_FILE_PATH:-.env}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

load_env_file() {
    if [ -f "$ENV_FILE_PATH" ]; then
        print_info "Loading environment from $ENV_FILE_PATH"
        set -a
        # shellcheck disable=SC1090
        source "$ENV_FILE_PATH"
        set +a
    fi
}

fetch_secrets_if_needed() {
    local should_fetch="false"

    if [ ! -f "$ENV_FILE_PATH" ]; then
        print_warn "$ENV_FILE_PATH not found; attempting to fetch secrets from AWS"
        should_fetch="true"
    elif [ "${FETCH_SECRETS:-false}" = "true" ]; then
        should_fetch="true"
    fi

    if [ "$should_fetch" = "true" ]; then
        if command -v aws >/dev/null 2>&1; then
            print_info "Fetching secrets via scripts/fetch-secrets.sh"
            if ! ENV_FILE="$ENV_FILE_PATH" SECRETS_DIR="$(pwd)" ./scripts/fetch-secrets.sh; then
                print_warn "Secrets fetch failed; continuing with existing environment"
            fi
        else
            print_warn "AWS CLI not available; skipping secrets fetch"
        fi
    fi
}

prepare_environment() {
    fetch_secrets_if_needed
    load_env_file

    export DEBUG_MODE="${DEBUG_MODE:-true}"
}

# Function to check if required files exist
check_requirements() {
    print_info "Checking requirements..."

    local missing=0

    if [ ! -f "secrets/box_config.json" ]; then
        print_error "Missing secrets/box_config.json"
        print_warn "  Copy secrets/box_config.json.example and configure it"
        missing=1
    fi

    if [ ! -f "config/config.yaml" ]; then
        print_error "Missing config/config.yaml"
        missing=1
    fi

    if [ ! -d "logs" ]; then
        print_warn "Creating logs directory..."
        mkdir -p logs
    fi

    if [ ! -d "output" ]; then
        print_warn "Creating output directory..."
        mkdir -p output
    fi

    if [ $missing -eq 1 ]; then
        print_error "Please fix missing requirements before running"
        exit 1
    fi

    print_info "All requirements met ✓"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: ./run.sh [COMMAND]

Commands:
  start       Start all services (docker-compose up)
  stop        Stop all containers
  restart     Restart all containers
  logs        Show logs from all services
  rebuild     Stop, rebuild from scratch, and restart all services
  build       Rebuild Docker images
  shell       Open shell in backend container
  status      Show container status
  help        Show this help message

Examples:
  ./run.sh start              # Start all services (frontend, backend, pipeline, mysql)
  FETCH_SECRETS=true ./run.sh start  # Pull secrets from AWS before starting
  ./run.sh logs               # View logs
  ./run.sh shell              # Open shell in backend container

Environment Variables:
  ENV_FILE_PATH=.env          Override the environment file to load
  FETCH_SECRETS=true          Force fetching secrets from AWS
  DEBUG_MODE=true             Enable debugger on port 5680
  MAPBOX_TOKEN=...            Your Mapbox token for map display

EOF
}

# Main command handler
case "${1:-help}" in
    start)
        prepare_environment
        check_requirements
        print_info "Starting all services..."
        print_info "App will be available at: http://localhost:80"
        print_warn "Press Ctrl+C to stop"
        docker-compose up
        ;;

    logs)
        print_info "Showing logs from all services..."
        docker-compose logs --tail=100 -f
        ;;

    restart)
        prepare_environment
        check_requirements
        print_info "Restarting all services..."
        docker-compose restart
        sleep 3
        docker-compose logs --tail=30
        ;;

    stop)
        print_info "Stopping containers..."
        docker-compose stop
        ;;

    clean)
        print_warn "This will remove containers and volumes..."
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_info "Stopping and removing containers..."
            docker-compose down -v
            print_info "Clean complete"
        else
            print_info "Cancelled"
        fi
        ;;

    build)
        prepare_environment
        print_info "Rebuilding Docker images..."
        docker-compose build --no-cache
        print_info "Build complete"
        ;;

    rebuild)
        prepare_environment
        check_requirements
        print_warn "Rebuilding stack from scratch (containers, images)..."
        docker-compose down --volumes --remove-orphans || true
        print_info "Building images with no cache..."
        docker-compose build --no-cache
        print_info "Starting services..."
        docker-compose up -d
        docker-compose ps
        ;;

    test)
        prepare_environment
        print_info "Running tests..."
        docker-compose run --rm backend python3 -m pytest tests/ -v || print_warn "No tests found or pytest not installed"
        ;;

    shell)
        prepare_environment
        print_info "Opening shell in backend container..."
        docker-compose exec backend /bin/bash || docker-compose run --rm backend /bin/bash
        ;;

    status)
        print_info "Container status:"
        docker-compose ps
        echo
        print_info "Recent activity:"
        docker-compose logs --tail=20
        ;;

    help|--help|-h)
        show_usage
        ;;

    *)
        print_error "Unknown command: $1"
        echo
        show_usage
        exit 1
        ;;
esac

