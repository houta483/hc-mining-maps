#!/bin/bash
# Borehole Analysis App - Initialization Script
# Run database initialization and setup tasks
#
# Usage: ./scripts/run_initialization.sh [compose-file]
# Example: ./scripts/run_initialization.sh docker-compose.prod.yml

set -e

COMPOSE_FILE="${1:-docker-compose.yml}"
SERVICE="${SERVICE:-backend}"

echo "🚀 Running Borehole App Initialization"
echo "======================================"
echo "Compose file: $COMPOSE_FILE"
echo "Service: $SERVICE"
echo ""

# Check if services are running
if ! docker compose -f "$COMPOSE_FILE" ps | grep -q "Up"; then
    echo "❌ Error: Docker Compose services are not running"
    echo "   Start services first: docker compose -f $COMPOSE_FILE up -d"
    exit 1
fi

echo "📋 Step 1: Verify database connection..."
docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" python3 -c "
import sys
sys.path.insert(0, '/app')
from src.api.database import Database
db = Database()
try:
    db.connect()
    print('✅ Database connection successful')
    db.close()
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    sys.exit(1)
"

echo ""
echo "📋 Step 2: Verify users table exists..."
docker compose -f "$COMPOSE_FILE" exec -T mysql mysql -u root -p\${MYSQL_ROOT_PASSWORD} ${MYSQL_DATABASE:-borehole_db} -e "
SELECT COUNT(*) as user_count FROM users;
" 2>/dev/null || echo "⚠️  Users table may not exist yet (will be created by init.sql)"

echo ""
echo "✅ Initialization verification complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Create admin user:"
echo "      docker compose -f $COMPOSE_FILE exec $SERVICE python3 /app/scripts/create_admin_user.py admin YOUR_PASSWORD"
echo ""
echo "   2. Test Box connection (if configured):"
echo "      docker compose -f $COMPOSE_FILE exec pipeline python3 /app/scripts/test_box_connection.py"
echo ""
echo "   3. Run pipeline (continuous mode):"
echo "      docker compose -f $COMPOSE_FILE logs -f pipeline"






