#!/bin/bash
# run_ingest.sh - Reads the HML files and writes the data to the RabbitMQ queue

# Goes into the container, activates the .venv/, runs the read script
docker exec docker-ingest-1 bash -c "cd /app && source .venv/bin/activate && python scripts/read_hml.py"
