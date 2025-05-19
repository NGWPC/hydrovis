#!/bin/bash
# run_rnr.sh - Runs T-Route based on the HML files and generates output .nc files

# Parse command line arguments
DETACH=false

# Function to handle termination
cleanup() {
  echo "Stopping container process..."
  docker exec docker-rnr-1 bash -c "pkill -f 'python main.py'"
  echo "Process terminated"
  exit 0
}

# Set up signal handling for Ctrl+C
trap cleanup SIGINT SIGTERM

# Run in foreground with proper signal handling
echo "Running in console (Ctrl+C will properly terminate the process)"
docker exec docker-rnr-1 bash -c "source ../../.venv/bin/activate && python main.py"
