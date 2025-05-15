#!/bin/bash
# run_rnr.sh - Runs T-Route based on the HML files and generates output .nc files

# Goes into the container, activates the .venv/, runs the read script
docker exec docker-rnr-1 bash -c "source ../../.venv/bin/activate && python main.py"
