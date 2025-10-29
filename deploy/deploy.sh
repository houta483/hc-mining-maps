#!/bin/bash
# Deployment script for production server

set -e

cd /opt/fmmap

echo "Pulling latest Docker images..."
docker-compose -f docker-compose.prod.yml pull

echo "Starting services..."
docker-compose -f docker-compose.prod.yml up -d --no-deps pipeline

echo "Waiting for health check..."
sleep 10

echo "Checking service status..."
docker-compose -f docker-compose.prod.yml ps

echo "Recent logs:"
docker-compose -f docker-compose.prod.yml logs --tail=50 pipeline

echo "Deployment complete!"

