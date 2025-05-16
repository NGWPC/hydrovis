#!/bin/bash
# start.sh - Builds and starts all services in the correct order

# Set error handling
set -e

# Function to check if a service is healthy
check_service_health() {
    local service=$1
    local port=$2
    local max_attempts=$3
    local wait_time=$4
    local endpoint=$5
    local attempt=1

    echo "Waiting for $service to be ready..."
    
    while [ $attempt -le $max_attempts ]; do
        if [ -n "$endpoint" ]; then
            # For services with specific health endpoints
            curl -s "http://localhost:$port$endpoint" > /dev/null 2>&1
        else
            # For services that just need port checking
            nc -z localhost $port > /dev/null 2>&1
        fi
        
        if [ $? -eq 0 ]; then
            echo "$service is now available!"
            return 0
        fi
        
        echo "Attempt $attempt/$max_attempts: $service not ready yet, waiting ${wait_time}s..."
        sleep $wait_time
        attempt=$((attempt + 1))
    done
    
    echo "Error: $service did not become ready in time."
    return 1
}

# Step 1: Build all images
echo "Building all Docker images..."
docker compose build

# Step 2: Start RabbitMQ and Redis first
echo "Starting infrastructure services (RabbitMQ and Redis)..."
docker compose up -d rabbitmq redis

# Step 3: Wait for RabbitMQ to be ready
check_service_health "RabbitMQ" 15672 30 5 "/api/aliveness-test/%2F" || { echo "RabbitMQ failed to start properly"; exit 1; }

# Step 4: Wait for Redis to be ready
check_service_health "Redis" 6379 10 2 || { echo "Redis failed to start properly"; exit 1; }

# Step 5: Start the rest of the services in detached mode
echo "Starting application services..."
docker compose up -d process_flows rnr ingest

echo "All services have been started successfully!"
echo "Use './run_ingest.sh', './run_rnr.sh', or './run_post_process.sh' to run specific services individually."
echo "Use './stop.sh' to stop all services when done."
echo "Use './logs.sh' to view service logs."
