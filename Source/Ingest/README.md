# hml_reader
Reads the weather.gov API  JSON-LD and pushes results to a Message Queue

## Getting Started

### Set up a virtual env
```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Get Rabbit MQ started
```bash
docker compose -f docker/compose.yaml up
```

### Run the script to read all HML from api.weather.gov
```bash
python scripts/read_hml.py
```
