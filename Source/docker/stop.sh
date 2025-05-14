#!/bin/bash
# stop.sh - Stops all running services

echo "Stopping all services..."
docker compose --env-file config.env down

echo "All services have been stopped."
