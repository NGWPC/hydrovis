# Docker scripts

The provided compose files are meant to spin up replace and route as a container for developmental testing

## How to run:

Run:

```sh
docker compose -f docker/compose.yaml up
```


The services require a data directory. By default, it uses the `data` directory at the root of this repository. 

You can override this by setting the `RNR_DATA_PATH` environment variable before running docker-compose:

```sh
RNR_DATA_PATH=/path/to/your/data 
```
