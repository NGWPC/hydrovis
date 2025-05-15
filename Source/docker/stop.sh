#!/bin/bash
# stop.sh - Stops all running services

echo "Stopping all services..."
docker compose down

echo "All services have been stopped."
