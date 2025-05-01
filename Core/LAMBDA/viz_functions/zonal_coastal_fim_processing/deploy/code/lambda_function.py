import os
import subprocess
import json
import boto3
import geopandas as gpd
import rasterio
from rasterio import features
import sqlalchemy
import shutil
import numpy as np
import time
import gc
import duckdb 
from datetime import datetime
import traceback
from urllib.parse import urlparse 

# --- Helper Functions ---
def download_from_s3(s3_url, local_dir):
    """Downloads file from S3, preserving structure within local_dir."""
    print(f"Initiating download: {s3_url}")
    parsed_url = urlparse(s3_url)
    if not parsed_url.scheme == 's3':
        raise ValueError(f"URL does not start with s3://: {s3_url}")
    bucket = parsed_url.netloc
    s3_key = parsed_url.path.lstrip('/')
    if not bucket or not s3_key:
        raise ValueError(f"Could not parse S3 URL: {s3_url}")

    # Construct local path, mirroring S3 key structure inside local_dir
    local_path = os.path.join(local_dir, s3_key)
    local_target_dir = os.path.dirname(local_path)
    os.makedirs(local_target_dir, exist_ok=True)

    s3 = boto3.client('s3')
    print(f"  Downloading: s3://{bucket}/{s3_key} -> {local_path}")
    try:
        s3.download_file(bucket, s3_key, local_path)
        print("  Download successful.")
        return local_path
    except Exception as e:
        print(f"ERROR during S3 download: {e}")
        traceback.print_exc()
        raise

def upload_to_s3(local_path, s3_url):
    """Uploads a local file to a full S3 URL."""
    print(f"Initiating upload: {local_path} -> {s3_url}")
    parsed_url = urlparse(s3_url)
    if not parsed_url.scheme == 's3':
        raise ValueError(f"URL does not start with s3://: {s3_url}")
    bucket = parsed_url.netloc
    s3_key = parsed_url.path.lstrip('/')
    if not bucket or not s3_key:
         raise ValueError(f"Could not parse S3 URL: {s3_url}")

    s3 = boto3.client('s3')
    print(f"  Uploading: {local_path} -> s3://{bucket}/{s3_key}")
    try:
        s3.upload_file(local_path, bucket, s3_key)
        print(f"  Successfully uploaded.")
        return s3_url
    except Exception as e:
        print(f"ERROR during S3 upload: {e}")
        traceback.print_exc()
        raise


def vectorize_binary_extent(raster_path, extent_field_name='inundated'):
    """
    Reads a depth raster, creates a binary version (1 where depth > 0),
    polygonizes the binary raster, and returns a GeoDataFrame of the extent.
    """
    print(f"Vectorizing binary extent from: {raster_path}")
    gdf_polygons = None
    image_depth = None
    binary_image = None
    feature_list = []

    if not os.path.exists(raster_path):
         print(f"ERROR: Input raster file not found: {raster_path}")
         return None

    try:
        with rasterio.open(raster_path) as src:
            print("  Reading depth raster...")
            image_depth = src.read(1, masked=False).astype(rasterio.float32)
            transform = src.transform
            raster_crs = src.crs
            nodata_value = src.nodata
            print(f"  Raster details: CRS={raster_crs}, Shape={image_depth.shape}, NoData={nodata_value}")

            # Create binary image (1=wet, 0=dry/nodata), using uint8 for efficiency
            print("  Binarizing depth raster...")
            binary_image = np.zeros(image_depth.shape, dtype=np.uint8)
            wet_mask = image_depth > 0
            if nodata_value is not None:
                nodata_mask = np.isnan(image_depth) if np.isnan(nodata_value) else (image_depth == nodata_value)
                final_wet_mask = wet_mask & ~nodata_mask
            else:
                final_wet_mask = wet_mask
            binary_image[final_wet_mask] = 1
            print("  Binarization complete.")

            # Release memory of large arrays no longer needed
            print("  Releasing intermediate raster memory...")
            del image_depth, wet_mask, final_wet_mask
            if 'nodata_mask' in locals(): del nodata_mask
            gc.collect()

            # Extract vector polygons from the binary raster where value is 1
            polygonization_mask = (binary_image == 1)
            print("  Extracting shapes (polygonizing)...")
            shapes_generator = features.shapes(binary_image, mask=polygonization_mask, transform=transform)
            # Convert generator to list for GeoDataFrame creation
            feature_list = [{'properties': {extent_field_name: 1}, 'geometry': s} for s, v in shapes_generator]
            print(f"  Generated {len(feature_list)} raw features.")

            if not feature_list:
                print("  No inundated features found.")
                gdf_polygons = gpd.GeoDataFrame({extent_field_name: []}, geometry=[], crs=raster_crs)
            else:
                print("  Creating GeoDataFrame...")
                gdf_polygons = gpd.GeoDataFrame.from_features(feature_list, crs=raster_crs)
                print(f"  Created GeoDataFrame with {len(gdf_polygons)} polygons.")
                # Release list memory after GDF is created
                print("  Releasing feature list memory...")
                del feature_list
                gc.collect()

    except Exception as e:
        print(f"ERROR during binary extent vectorization: {e}")
        traceback.print_exc()
        raise
    finally:
        # cleanup
        if 'binary_image' in locals() and binary_image is not None: del binary_image
        if 'feature_list' in locals(): del feature_list
        gc.collect()

    return gdf_polygons

def write_gdf_to_postgis(gdf, db_user, db_pass, db_host, db_name, target_schema, target_table, target_srid=3857):
    """Writes a GeoDataFrame to a PostGIS table."""
    if gdf is None or gdf.empty:
        print("Input GeoDataFrame is empty. Skipping PostGIS write.")
        return 0

    features_to_write = len(gdf)
    print(f"Attempting to write {features_to_write} features to PostGIS: {target_schema}.{target_table}")
    postgis_engine = None
    features_written_count = 0

    try:
        # Connect to the database
        conn_str = f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"
        postgis_engine = sqlalchemy.create_engine(conn_str, echo=False)

        # Reproject and ensure 'geom' column name before writing
        print(f"  Converting CRS from {gdf.crs} to EPSG:{target_srid}...")
        gdf_proj = gdf.to_crs(f"EPSG:{target_srid}")
        current_geom_col = gdf_proj.geometry.name
        if current_geom_col != 'geom':
            gdf_proj = gdf_proj.rename_geometry('geom')
            print(f"  Renamed geometry column from '{current_geom_col}' to 'geom'.")

        print(f"  Writing to PostGIS...")
        gdf_proj.to_postgis(
            name=target_table,
            con=postgis_engine,
            schema=target_schema,
            if_exists='append',
            index=False,
            chunksize=None # Write all at once; set e.g., 5000 if memory issues during write
        )
        features_written_count = features_to_write
        print(f"  Successfully wrote {features_written_count} features.")

    except ImportError as e:
         print(f"ERROR: Missing required DB libraries (psycopg2, sqlalchemy, etc.): {e}")
         raise e
    except Exception as e:
        print(f"ERROR writing features to PostGIS: {e}")
        traceback.print_exc()
        raise RuntimeError(f"PostGIS write failed: {e}")
    finally:
        # Ensure database connection is closed
        if postgis_engine:
            postgis_engine.dispose()
            print("  Database connection closed.")

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
        extent_attr_name = event.get("extent_attribute_name", "inundated") # Optional field for extent column name
        viz_db_database = os.environ["VIZ_DB_DATABASE"]
        viz_db_host = os.environ["VIZ_DB_HOST"]
        viz_db_username = os.environ["VIZ_DB_USERNAME"]
        viz_db_password = os.environ["VIZ_DB_PASSWORD"]
        output_s3_target_location = os.environ.get("OUTPUT_S3_TARGET_LOCATION") # Base S3 path string for output rasters

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

    # --- Ensure DuckDB spatial extension is loaded (if needed by zonal_fim.py) ---
    try:
        print(f"Ensuring DuckDB spatial extension is loaded for: {efs_duckdb_path}...")
        with duckdb.connect(efs_duckdb_path, read_only=False) as con:
            try:
                con.execute("LOAD spatial;")
                print("  Spatial extension already loaded.")
            except Exception:
                print(f"  Failed to load spatial extension, attempting install...")
                try:
                    con.execute("INSTALL spatial;")
                    con.execute("LOAD spatial;")
                    print("  Installed and loaded spatial extension.")
                except Exception as install_err:
                    print(f"  WARNING: Failed to install/load DuckDB spatial extension: {install_err}")
    except Exception as e:
        print(f"WARNING: Error during DuckDB spatial extension check: {e}")

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

    # --- Setup Local Temp Directory ---
    local_tmp_dir = "/tmp/zonal_coastal_run"
    print(f"\nUsing temporary directory: {local_tmp_dir}")
    if os.path.exists(local_tmp_dir):
        print(f"  Cleaning up existing temporary directory...")
        try: shutil.rmtree(local_tmp_dir)
        except Exception as e: print(f"  Warning: Could not remove existing tmp directory: {e}")
    os.makedirs(local_tmp_dir, exist_ok=True)

    # Initialize state variables
    local_nc_path = None
    depth_local_output = None
    wse_local_output = None
    final_depth_path = None
    final_wse_path = None
    total_features_written = 0

    try:
        # === Stage 1: Download Input NetCDF ===
        stage_start_time = time.time()
        print(f"\n--- Stage 1: Downloading Input NetCDF ---")
        local_nc_path = download_from_s3(s3_input_path, local_tmp_dir)
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
        python_executable = "/opt/conda/envs/coastal_fim_vis/bin/python" 
        zonal_fim_script = "/var/task/zonal_fim.py"

        cmd = [
            python_executable, zonal_fim_script,
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
            # Provide detailed error info if script fails
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
            extent_gdf = vectorize_binary_extent(depth_local_output, extent_attr_name)
            if extent_gdf is not None and not extent_gdf.empty:
                db_write_start = time.time()
                written = write_gdf_to_postgis(
                    gdf=extent_gdf, db_user=viz_db_username, db_pass=viz_db_password,
                    db_host=viz_db_host, db_name=viz_db_database, target_schema=target_schema,
                    target_table=target_table, target_srid=3857
                )
                total_features_written += written
                print(f"  PostGIS write duration: {time.time() - db_write_start:.2f}s.")
                print("  Releasing GeoDataFrame memory...")
                del extent_gdf
                gc.collect()
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
            # Combine base prefix (e.g., 'test_lambda_output_tif') with dynamic path
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
                final_depth_path = upload_to_s3(depth_local_output, output_depth_path_s3)
            else:
                print(f"  Skipping depth raster upload, local file not found: {depth_local_output}")

            # Upload WSE Raster
            if os.path.exists(wse_local_output):
                final_wse_path = upload_to_s3(wse_local_output, output_wse_path_s3)
            else:
                print(f"  Skipping WSE raster upload, local file not found: {wse_local_output}")
            print(f"Stage 5 duration: {time.time() - stage_start_time:.2f}s")

    except Exception as e:
        # Catch-all for errors during the main processing stages
        print(f"\n!!! FATAL ERROR in lambda_handler processing stage !!!")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Details: {e}")
        traceback.print_exc()
        print("Attempting cleanup after error...")
        if os.path.exists(local_tmp_dir):
            try: shutil.rmtree(local_tmp_dir)
            except Exception as clean_e: print(f"Warning: Could not remove tmp dir {local_tmp_dir} on error: {clean_e}")
        # Indicate failure
        return {"statusCode": 500, "body": json.dumps(f"Lambda failed: {type(e).__name__}: {str(e)}")}
    finally:
        # --- Final Cleanup ---
        print(f"\n--- Final Cleanup ---")
        if os.path.exists(local_tmp_dir):
            print(f"Cleaning up temporary directory: {local_tmp_dir}...")
            try:
                shutil.rmtree(local_tmp_dir)
                print(f"  Removed tmp directory tree.")
            except Exception as e:
                print(f"  Warning: Could not remove tmp directory {local_tmp_dir}: {e}")
        else:
            print("  Temporary directory not found or already removed.")

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