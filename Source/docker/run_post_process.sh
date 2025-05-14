#!/bin/bash
# run_rnr.sh - Formats the .nc files to create output csvs

# Goes into the container, activates the .venv/, runs the read script
docker exec docker-process_flows-1 bash -c "cd /app && source ../../venv/bin/activate && python post_process.py"
