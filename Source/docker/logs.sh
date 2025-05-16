#!/bin/bash
# logs.sh - Shows logs from all running services

if [ "$#" -eq 0 ]; then
    # No arguments, show logs from all services
    docker compose logs -f
else
    # Show logs for specified service
    docker compose logs -f "$@"
fi
