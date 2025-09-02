#!/bin/bash
# run_post_process.sh - Formats the .nc files to create output csvs

# Goes into the container, activates the .venv/, runs the read script
docker exec docker-rnr-1 bash -c "source ../../.venv/bin/activate && python post_process.py"
