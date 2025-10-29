#!/bin/bash
# Borehole Analysis Pipeline - Run Script
# Runs pipeline with Mapbox web server

set -e
export USE_LOCAL_DATA=true
export DEBUG_MODE=true

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

# Function to check if required files exist
check_requirements() {
    print_info "Checking requirements..."
    
    local missing=0
    
    # Check if using local data mode
    if [ "${USE_LOCAL_DATA:-false}" != "true" ] && [ ! -f "secrets/box_config.json" ]; then
        print_error "Missing secrets/box_config.json"
        print_warn "  Copy secrets/box_config.json.example and configure it"
        print_warn "  Or set USE_LOCAL_DATA=true to use test data"
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
  build       Rebuild Docker images
  shell       Open shell in backend container
  status      Show container status
  help        Show this help message

Examples:
  ./run.sh start              # Start all services (frontend, backend, pipeline, mysql)
  ./run.sh logs               # View logs
  USE_LOCAL_DATA=true ./run.sh start  # Use test data instead of Box
  ./run.sh shell              # Open shell in backend container

Environment Variables:
  USE_LOCAL_DATA=true         Use local test data instead of Box
  DEBUG_MODE=true             Enable debugger on port 5680
  MAPBOX_TOKEN=...            Your Mapbox token for map display

EOF
}

# Main command handler
case "${1:-help}" in
    start)
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
        print_info "Rebuilding Docker images..."
        docker-compose build --no-cache
        print_info "Build complete"
        ;;
    
    test)
        print_info "Running tests..."
        docker-compose run --rm backend python3 -m pytest tests/ -v || print_warn "No tests found or pytest not installed"
        ;;
    
    shell)
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

