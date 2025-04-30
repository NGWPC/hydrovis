#!/bin/bash
# This script activates the coastal_fim_vis conda environment and runs awslambdaric.
exec conda run -n coastal_fim_vis --no-capture-output python -m awslambdaric "$@"