import os
import subprocess
import json
import geopandas as gpd
import rasterio
from rasterio import features
import sqlalchemy
import numpy as np
import time
from datetime import datetime
import traceback
from urllib.parse import urlparse 
import fsspec
import tempfile
import operator
from shapely.geometry import shape

# Initialize S3 filesystem
try:
    FS_S3 = fsspec.filesystem('s3')
    print("Initialized global fsspec S3 filesystem.")
except Exception as e_fs:
    print(f"FATAL ERROR: Failed to initialize global fsspec S3 filesystem during INIT: {e_fs}")
    traceback.print_exc()
    raise e_fs

# Read DB credentials globally
try:
    VIZ_DB_DATABASE = os.environ["VIZ_DB_DATABASE"]
    VIZ_DB_HOST = os.environ["VIZ_DB_HOST"]
    VIZ_DB_USERNAME = os.environ["VIZ_DB_USERNAME"]
    VIZ_DB_PASSWORD = os.environ["VIZ_DB_PASSWORD"]
except KeyError as e_env:
    print(f"FATAL ERROR: Missing database environment variable during INIT: {e_env}")
    raise ValueError(f"Missing database environment variable: {e_env}") from e_env

# Initialize SQLAlchemy Engine globally
try:
    DB_CONN_STR = f"postgresql://{VIZ_DB_USERNAME}:{VIZ_DB_PASSWORD}@{VIZ_DB_HOST}/{VIZ_DB_DATABASE}"
    POSTGIS_ENGINE = sqlalchemy.create_engine(DB_CONN_STR, echo=False, pool_pre_ping=True) 
    print(f"Initialized global SQLAlchemy engine for {VIZ_DB_HOST}.")
except Exception as e_db:
    print(f"FATAL ERROR: Failed to initialize global SQLAlchemy engine during INIT: {e_db}")
    traceback.print_exc()
    raise e_db

# --- Helper Functions ---
def vectorize_binary_extent(raster_path):
    """
    Reads a depth raster, creates a binary version (1 where depth > 0),
    polygonizes the binary raster, and returns a GeoDataFrame of the extent.
    """
    print(f"Vectorizing binary extent from: {raster_path}")
    gdf_polygons = None
    try:
        with rasterio.open(raster_path) as src:
            print("  Reading depth raster as masked array...")
            image_depth = src.read(1, out_dtype='float32', masked=True)
            transform = src.transform
            raster_crs = src.crs
            print(f"  Raster details: CRS={raster_crs}, Shape={image_depth.shape}, NoData={src.nodata}")
            print("  Creating mask for depth > 0...")
            masked = np.ma.masked_less_equal(image_depth, 0, copy=False)
            mask = ~masked.mask
            data = mask.view('uint8')
            del masked, image_depth
            print("  Polygonizing masked raster...")
            raster_shapes = map(operator.itemgetter(0), features.shapes(data, mask=mask, transform=transform))
            gdf_polygons = gpd.GeoDataFrame(crs=raster_crs, geometry=list(map(shape, raster_shapes)))
            print(f"  Created GeoDataFrame with {len(gdf_polygons)} polygons.")
    except Exception as e:
        print(f"ERROR during binary extent vectorization: {e}")
        traceback.print_exc()
        raise
    return gdf_polygons

def write_gdf_to_postgis(gdf, postgis_engine, target_schema, target_table, target_srid=3857):
    """
    Writes a GeoDataFrame to a PostGIS table using the provided SQLAlchemy engine.
    """
    if gdf is None or gdf.empty:
        print("Input GeoDataFrame is empty. Skipping PostGIS write.")
        return 0

    features_to_write = len(gdf)
    print(f"Attempting to write {features_to_write} features to PostGIS: {target_schema}.{target_table}")
    features_written_count = 0

    try:
        # Reproject and ensure 'geom' column name before writing
        print(f"  Converting CRS from {gdf.crs} to EPSG:{target_srid}...")
        gdf_proj = gdf.to_crs(f"EPSG:{target_srid}")
        current_geom_col = gdf_proj.geometry.name
        if current_geom_col != 'geom':
            gdf_proj = gdf_proj.rename_geometry('geom')
            print(f"  Renamed geometry column from '{current_geom_col}' to 'geom'.")

        print(f"  Writing to PostGIS...")
        # Use the passed-in engine for the connection
        gdf_proj.to_postgis(
            name=target_table,
            con=postgis_engine, 
            schema=target_schema,
            if_exists='append',
            index=False,
            chunksize=None 
        )
        features_written_count = features_to_write
        print(f"  Successfully wrote {features_written_count} features.")

    except Exception as e:
        print(f"ERROR writing features to PostGIS table {target_schema}.{target_table}: {e}")
        traceback.print_exc()
        raise 
    return features_written_count

# --- Main Lambda Handler ---
def lambda_handler(event, context):
    """
    Main handler: downloads NetCDF, runs zonal_fim.py to create rasters,
    vectorizes binary depth extent, writes extent to PostGIS, uploads rasters.
    Reads configuration from Step Functions event payload.
    """
    lambda_start_time = time.time()
    aws_request_id = context.aws_request_id if context else 'N/A'
    print(f"--- Zonal Coastal FIM Lambda Execution Started (ID: {aws_request_id}) ---")
    print(f"Received event:\n{json.dumps(event, indent=2)}")

    # --- Configuration ---
    print("\n--- Reading Configuration ---")
    config_name = None
    efs_duckdb_path = None
    output_s3_target_location = None
    try:
        # Read settings from the event payload passed by Step Functions
        config_name = event["config_name"]
        domain = event["domain"]
        forecast_type = event["forecast_type"]
        efs_duckdb_path = event["efs_duckdb_path"] 
        s3_input_path = event["input_s3_netcdf_path"] 
        target_db_table_full = event["target_db_table"]
        reference_time_str = event["reference_time"]
        output_s3_target_location = os.environ.get("OUTPUT_S3_TARGET_LOCATION")

        if output_s3_target_location and not output_s3_target_location.startswith("s3://"):
            raise ValueError(f"Invalid output_s3_target_location in event: {output_s3_target_location}")

        # Parse reference time for use in path construction
        try:
            reference_date = datetime.strptime(reference_time_str, "%Y-%m-%d %H:%M:%S")
            ref_time_ymd_str = reference_date.strftime("%Y%m%d")
        except ValueError as e:
            raise ValueError(f"Could not parse reference_time '{reference_time_str}': {e}")

    except KeyError as e:
        print(f"FATAL ERROR: Missing required key in event payload or environment variable: {e}")
        raise ValueError(f"Missing required configuration key: {e}")
    except Exception as e:
        print(f"FATAL ERROR: Error reading configuration: {e}")
        traceback.print_exc()
        raise e

    # --- Validate Input DuckDB Path ---
    print(f"\nValidating input DuckDB path: {efs_duckdb_path}")
    if not os.path.exists(efs_duckdb_path):
         raise FileNotFoundError(f"Input DuckDB path does not exist: {efs_duckdb_path}")
    print("Input DuckDB path validation successful.")

    # --- Parse Target DB Info ---
    try:
        target_schema, target_table = target_db_table_full.split('.')
    except ValueError:
        raise ValueError(f"Invalid target_db_table format in event (must be 'schema.table'): {target_db_table_full}")

    # --- Print Configuration Summary ---
    print("\n--- Effective Configuration ---")
    print(f"  Config Name: {config_name}")
    print(f"  Domain: {domain}")
    print(f"  Forecast Type: {forecast_type}")
    print(f"  Input DuckDB Path (EFS): {efs_duckdb_path}")
    print(f"  Input NetCDF Path (S3): {s3_input_path}")
    print(f"  Target PostGIS Table: {target_schema}.{target_table}")
    print(f"  Reference Time: {reference_time_str}")
    print(f"  Output S3 Target: {output_s3_target_location}")
    print(f"--- End Configuration ---")

    # Initialize state variables
    local_nc_path = None
    depth_local_output = None
    wse_local_output = None
    final_depth_path = None
    final_wse_path = None
    total_features_written = 0

    try:
        with tempfile.TemporaryDirectory() as local_tmp_dir:
            print(f"Using temporary directory: {local_tmp_dir}")
            
            # === Stage 1: Download Input NetCDF ===
            stage_start_time = time.time()
            print(f"\n--- Stage 1: Downloading Input NetCDF ---")
            local_nc_path = os.path.join(local_tmp_dir, os.path.basename(s3_input_path))
            FS_S3.get(s3_input_path, local_nc_path)
            if not os.path.exists(local_nc_path):
                raise FileNotFoundError(f"S3 download failed or file not found locally after get: {local_nc_path}")
            print(f"Stage 1 duration: {time.time() - stage_start_time:.2f}s")

            # === Stage 2: Prepare Local Raster Paths ===
            stage_start_time = time.time()
            print(f"\n--- Stage 2: Preparing Local Raster Paths ---")
            file_name = os.path.basename(local_nc_path)
            base = os.path.splitext(file_name)[0]
            depth_local_output = os.path.join(local_tmp_dir, f"{base}_depth_local.tif")
            wse_local_output   = os.path.join(local_tmp_dir, f"{base}_wse_local.tif")
            print(f"  Local Depth Output: {depth_local_output}")
            print(f"  Local WSE Output: {wse_local_output}")
            print(f"Stage 2 duration: {time.time() - stage_start_time:.2f}s")

            # === Stage 3: Run zonal_fim.py ===
            stage_start_time = time.time()
            print(f"\n--- Stage 3: Running zonal_fim.py ---")
            zonal_fim_script = "/home/code/zonal_fim.py"

            cmd = [
                "python", zonal_fim_script,
                "--execute", "True", "--preprocess", "False", "--generate_mask", "False",
                "--generate_wse", "True", "--generate_depth", "True", "--zarr_format", "False",
                "--dissolve", "False",
                "-i", local_nc_path, "-c", efs_duckdb_path,
                "-m", depth_local_output, "-q", wse_local_output
            ]
            print(f"Executing command: {' '.join(cmd)}")
            try:
                result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8')
                print(f"  zonal_fim.py stdout (tail): {result.stdout[-1000:]}")
                print(f"  zonal_fim.py stderr (tail): {result.stderr[-1000:]}")
                print(f"  zonal_fim.py completed successfully.")
            except subprocess.CalledProcessError as e:
                print(f"FATAL ERROR: zonal_fim.py failed (Code: {e.returncode})")
                print(f"  Command: {' '.join(e.cmd)}")
                print(f"  Stderr:\n{e.stderr}")
                print(f"  Stdout:\n{e.stdout}")
                raise
            print(f"Stage 3 duration: {time.time() - stage_start_time:.2f}s")

            # === Stage 4: Vectorize Extent & Write to PostGIS ===
            stage_start_time = time.time()
            print(f"\n--- Stage 4: Vectorizing Extent & Writing to PostGIS ---")
            extent_gdf = None

            if not os.path.exists(depth_local_output):
                print(f"WARNING: Depth raster not found ({depth_local_output}). Skipping Stage 4.")
            else:
                extent_gdf = vectorize_binary_extent(depth_local_output)
                if extent_gdf is not None and not extent_gdf.empty:
                    db_write_start = time.time()
                    written = write_gdf_to_postgis(
                        gdf=extent_gdf,
                        postgis_engine=POSTGIS_ENGINE,
                        target_schema=target_schema,
                        target_table=target_table,
                        target_srid=3857
                    )
                    total_features_written += written
                    print(f"  PostGIS write duration: {time.time() - db_write_start:.2f}s.")
                    del extent_gdf
                else:
                    print("  No vector features generated or written to PostGIS.")
            print(f"Stage 4 duration: {time.time() - stage_start_time:.2f}s")

            # === Stage 5: Construct S3 Output Paths & Upload Rasters ===
            if output_s3_target_location:
                parsed_target_uri = urlparse(output_s3_target_location)
                output_s3_bucket = parsed_target_uri.netloc
                output_s3_base_prefix = parsed_target_uri.path.lstrip('/')
                print(f"Output Target Parsed: Bucket='{output_s3_bucket}', Base Prefix='{output_s3_base_prefix}'")
                stage_start_time = time.time()
                print(f"\n--- Stage 5: Constructing S3 Output Paths & Uploading Rasters ---")

                # Define dynamic sub-folder structure: <domain>/<forecast_type>/<YYYYMMDD>
                dynamic_subfolder_path = f"{domain}/{forecast_type}/{ref_time_ymd_str}"
                # Combine base prefix with dynamic path
                full_base_key = os.path.join(output_s3_base_prefix, dynamic_subfolder_path).replace("\\","/")
                # Use the unique config_name for the output filenames
                output_base_filename = config_name

                # Define final S3 keys
                depth_s3_key = f"{full_base_key}/{output_base_filename}_depth_raster.tif"
                wse_s3_key = f"{full_base_key}/{output_base_filename}_wse_raster.tif"

                # Construct full S3 URIs
                output_depth_path_s3 = f"s3://{output_s3_bucket}/{depth_s3_key}"
                output_wse_path_s3 = f"s3://{output_s3_bucket}/{wse_s3_key}"
                print(f"  Constructed Output Depth Path S3: {output_depth_path_s3}")
                print(f"  Constructed Output WSE Path S3: {output_wse_path_s3}")

                # Upload Depth Raster
                if os.path.exists(depth_local_output):
                    final_depth_path = output_depth_path_s3
                    FS_S3.put(depth_local_output, final_depth_path)
                else:
                    print(f"  Skipping depth raster upload, local file not found: {depth_local_output}")

                # Upload WSE Raster
                if os.path.exists(wse_local_output):
                    final_wse_path = output_wse_path_s3
                    FS_S3.put(wse_local_output, final_wse_path)
                else:
                    print(f"  Skipping WSE raster upload, local file not found: {wse_local_output}")
                print(f"Stage 5 duration: {time.time() - stage_start_time:.2f}s")

    except Exception as e:
        # Catch-all for errors during the main processing stages
        print(f"\n!!! FATAL ERROR in lambda_handler processing stage !!!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {e}")
        traceback.print_exc()
        raise

    finally:
        # --- Final Report ---
        lambda_end_time = time.time()
        total_duration = lambda_end_time - lambda_start_time
        print(f"\n--- Lambda Execution Summary ---")
        print(f"Total execution duration: {total_duration:.2f} seconds.")
        print(f"Config Name processed: {config_name}")
        print(f"Features written to PostGIS: {total_features_written}")
        if final_depth_path: print(f"Depth raster uploaded to: {final_depth_path}")
        if final_wse_path: print(f"WSE raster uploaded to: {final_wse_path}")
        print(f"--- End Lambda Execution (ID: {aws_request_id}) ---")

    # --- Return Success ---
    return_body = {
        "message": f"Processing complete for {config_name}. Wrote {total_features_written} features to {target_db_table_full}.",
        "config_name": config_name,
        "input_processed": s3_input_path,
        "duckdb_used": efs_duckdb_path,
        "outputDepthPath": final_depth_path, 
        "outputWsePath": final_wse_path,     
        "features_written": total_features_written,
        "target_table": target_db_table_full
    }
    print(f"\nLambda finished successfully. Return body:\n{json.dumps(return_body, indent=2)}")
    return { "statusCode": 200, "body": json.dumps(return_body) }