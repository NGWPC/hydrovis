# Replace and Route (v2025.6.0)

Replace and route is a service which routes streamflow forecasts from the [NWPS API](https://api.water.noaa.gov/nwps/v1/docs/#/) through T-Route to propogate flow through a river segment. Outputs are shown at [water.noaa.gov](water.noaa.gov). This `Source/` dir contains a collection of code, docker management scripts, and IaC to run the full collection of services. 

## Overview

There are two versions of Replace and Route contained in `hydrovis/`
- The Docker Development Version
    - This version is what can be spun up locally within a User's environment if they were to clone the repo
- IaC version
    - This is the production version which will is designed to scale efficiently to handle many t-route containers running in parallel
    - This code is contained in `Source/terraform`

Both versions are the same code, but the terraform IaC is what is designed to scale. The docker version is meant to be a localized testing version

## Requirements

The following data is required to run RnR locally
- the v2.2 hydrofabric layers stored as parquet files
    - These are located at `s3://hydrofabric-data/icefabric` from the Raytheon private S3 bucket. Please contact @taddyb for these files if you do not have access
- `docker compose` installed on your system

## Parts
![RnR Workflow](rnr_workflow.png)

There are three parts to replace and route
1. The HML Ingestion 
    - This code reads in HML files from the public [weather api](https://api.weather.gov/) and queues them into a Rabbit MQ. Redis is used to cache previously read forecasts. This code is located in `Source/Ingest`
    - To run this, run `./run_ingest.sh` after starting the containers
2. T-Route
    - This is the routing code which will propograte forecasted flow downstream. All code is located in `src/troute-rnr` directory and the `Source/RnR` contains the docker scripts to run T-Route.
    - To run this, run `./run_rnr.sh` after starting the containers
3. Post-processing
    - This is the code which will read T-Route outputs and create and `output-inundation.csv` file
    - To run this, run `./run_post_process.sh` after starting the containers

### How to run
To run RnR you can run the following scripts:
```sh
cd Source/docker
./start.sh
./run_ingest.sh
./run_rnr.sh
./run_post_process.sh
./stop.sh
```
and you can view the logs through `./logs.sh`

