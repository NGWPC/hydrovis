# Distributions

The files in this repo are wheels from the internal NGWPC icefabric repo. Each package has a service(s) designed to extract RnR segments and format the hydrofabric v2.2

## How to use:
- These files are built in the T-Route RnR docker containers and run the `rnr.get_rnr_segment()`
- These Wheels are required to run `troute-rnr/`

## Why are there wheels instead of a github install?
- Since the `icefabric/` repo has not been delivered at this time, we've attached wheels from a version that works with replace and route to ensure the code will run

## The `get_rnr_segment()` Function used in RnR

### Overview

The `get_rnr_segment` function extracts a river network segment from a hydrofabric dataset based on RnR (Reach and Route) rules. It processes hydrologic data from an Iceberg catalog and exports the results as a multi-layer GeoPackage file.

### Function Signature

```python
def get_rnr_segment(catalog: Catalog, reach_id: str, output_file: str) -> gpd.GeoDataFrame
```

### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `catalog` | `Catalog` | The Iceberg catalog containing the hydrofabric data tables |
| `reach_id` | `str` | The reach identifier (hf_id) from the NWPS API used to locate the target stream segment |
| `output_file` | `str` | File path where the output GeoPackage will be saved |

### Returns

- **Type**: `gpd.GeoDataFrame`
- **Description**: A GeoDataFrame containing the processed hydrofabric data

### Data Sources

The function accesses the following tables from the hydrofabric. These are parquet files of each layer which are available from the raytheon s3:// or can be built from the hydrofabric v2.2 gpkg file through a geopandas parquet conversion.

### Processing Logic

1. **Stream Identification**: Locates the target stream using the provided `reach_id`
2. **Mainstem Filtering**: Identifies all streams on the same mainstem with hydrosequence values less than or equal to the target stream
3. **Stream Order Matching**: Filters features to include only those with the same stream order as the target reach
4. **Geometric Data Extraction**: Retrieves associated geometric and attribute data for:
   - Flowpaths
   - Nexus points
   - Divides
   - Points of interest
   - Hydrolocations
5. **Multi-layer Export**: Saves all processed data as separate layers in a single GeoPackage file

### Output Structure

The function creates a GeoPackage file with the following layers:
- `flowpaths`
- `nexus`
- `divides`
- `divide-attributes`
- `network`
- `pois`
- `flowpath-attributes-ml`
- `flowpath-attributes`
- `hydrolocations`

### Usage Example

```python
from icefabric_manage import build
from icefabric_tools import rnr
from pyiceberg.catalog import load_catalog

# Builds the catalog
data_dir = <YOUR DATA DIR>
self.catalog_settings = {
    "type": "sql",
    "uri": f"sqlite:///{str(data_dir / 'warehouse/pyiceberg_catalog.db')}",
    "warehouse": f"file://{str(data_dir.resolve())}/warehouse",
}

self.catalog = load_catalog("hydrofabric", **self.catalog_settings)
build(self.catalog, Path(f"{self.data_dir.resolve()}/parquet"))

# Extract RnR segment
gdf = rnr.get_rnr_segment(settings.catalog, inputs.reach.id, settings.tmp_geopackage)
```
