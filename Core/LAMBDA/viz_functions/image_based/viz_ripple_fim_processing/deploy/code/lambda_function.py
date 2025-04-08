import sys
import boto3
import botocore
import os
from urllib.parse import urlparse
from datetime import datetime
import re
import subprocess
import json
import shutil
import traceback

from loguru import logger

import geopandas
from sqlalchemy import create_engine

import rasterio
import geopandas as gpd
from shapely.geometry import Polygon
import numpy as np
import pandas as pd
import math
import unicodedata

from rasterio import features
from io import StringIO

import tracemalloc

#from osgeo import gdal
#print(gdal.__version__)

######################################################################################

s3 = boto3.resource('s3')
s3_client = boto3.client('s3')

######################################################################################

class MissingS3FileException(Exception):
    """ my custom exception class """

def parse_s3_url_GET_bucket_key(url):
    """Parses an S3 URL into bucket name and object key."""

    parsed_url = urlparse(url)

    if parsed_url.scheme != 's3':
        raise ValueError("Invalid S3 URL")

    bucket_name = parsed_url.netloc
    key = parsed_url.path.lstrip('/')

    return bucket_name, key

def parse_s3_url_GET_bucket_key_filename(url):
    """Parses an S3 URL into bucket, key, and filename."""
    parsed_url = urlparse(url)
    if parsed_url.scheme != "s3":
        raise ValueError("Invalid S3 URL")
    bucket = parsed_url.netloc
    key = parsed_url.path.lstrip("/")
    filename = key.split("/")[-1]
    return bucket, key, filename

def check_boolean_value(variable):
    """
    Checks if the variable is a boolean type or string.

    Parameters:
        variable: value to prase.

    Returns:
        bool: True if exists, False otherwise
    """
    if isinstance(variable,bool):
        return variable
    else:
        return variable.strip().lower() == "true"

def check_environment_value(variable):
    """
    Checks if the variable is a valid string.

    Parameters:
        variable: value to prase.

    Returns:
        bool: True if exists, False otherwise
    """
    if not variable.strip():
        return False
    if len(variable) == 0:
        return False
    if not variable:
        return False
    if variable is None:
        return False

    return True

def normalize(column: str) -> str:
    """
    Normalize column name by replacing invalid characters with underscore
    strips accents and make lowercase
    :param column: column name
    :return: normalized column name
    """
    n = re.sub(r"[ ,;{}()\n\t=]+", '_', column.lower())
    return unicodedata.normalize('NFKD', n).encode('ASCII', 'ignore').decode()

def rename_columns_by_type(df, type_mapping):
    """
    Renames columns of a Pandas DataFrame based on their data type.

    Args:
        df (pd.DataFrame): The DataFrame to rename columns in.
        type_mapping (dict): A dictionary where keys are data types (e.g., 'int64', 'object')
                             and values are functions that take a column name as input and return
                             the new column name.

    Returns:
        pd.DataFrame: A new DataFrame with renamed columns.
    """
    new_columns = []
    for col in df.columns:
        col_type = df[col].dtype
        rename_func = type_mapping.get(str(col_type))
        if rename_func:
            new_col_name = rename_func(col)
            new_columns.append(new_col_name)
        else:
            new_columns.append(col)
    df.columns = new_columns
    return df

def raster_to_geoparquet(raster_path, input_fid, input_stage, input_extent):

    with rasterio.open(raster_path) as src:
        band = src.read(1)
        #mask = band != src.nodata
        #mask = band != 0
        values_to_mask = [1] #1 is the value we want to keep
        raster_data = src.read(1)
        mask = np.isin(raster_data, values_to_mask)

        #shapes = rasterio.features.shapes(band, mask=mask, transform=src.transform)
        shapes = rasterio.features.shapes(band, mask=mask, transform=src.transform)

        polygons = []
        values = []
        for geom, val in shapes:
            polygons.append(Polygon(geom['coordinates'][0]))
            values.append(val)

        gdf = gpd.GeoDataFrame({'feature_id': input_fid, 'stage_ft': input_stage, 'discharge_cfs': input_extent , 'geometry': polygons}, crs=src.crs)
        
        # Dissolve all geometries into one
        dissolved_gdf = gdf.dissolve(by='feature_id')

#03-18-25        gdf = gpd.GeoDataFrame({'FeatureID': input_fid, 'Stage': input_stage, 'Flows': input_extent , 'geometry': polygons}, crs=src.crs)
        #gdf = gpd.GeoDataFrame({'FID': input_fid, 'STAGE': input_stage, 'FLOWS': input_extent , 'geometry': polygons}, crs=src.crs)
        #gdf = gpd.GeoDataFrame({'FID': "X_" + str(input_fid), 'STAGE': "X_" + str(input_stage), 'FLOWS': "X_" + str(input_extent) , 'geometry': polygons}, crs=src.crs)

        #return gdf
        return dissolved_gdf

       #    dn integer,
        #FeatureID bigint,
        #Stage bigint,
        #Flows bigint,

def query_parquet_in_chunks(file_path, chunksize, query_expression):
    """
    Reads a Parquet file in chunks, applies a query to each chunk,
    and concatenates the results.

    Args:
        file_path (str): Path to the Parquet file.
        chunksize (int): Number of rows to read per chunk.
        query_expression (str): Query expression to apply to each chunk
                                (e.g., 'column_name > 10').

    Returns:
        pandas.DataFrame: DataFrame containing the results of the query.
    """
    all_results = []
    for chunk in pd.read_parquet(file_path, chunksize=chunksize):
        result_chunk = chunk.query(query_expression)
        all_results.append(result_chunk)
    return pd.concat(all_results)

def track_changes(
        env_db_username,
        env_db_password,
        env_db_host,
        env_db_database,
        env_db_tracking_schema,
        env_db_tracking_table_name,
        tracking_input_model_name,
        skipped_count,
        process_count,
        error_location,
        time_difference,
        peak_memory):

    try:
        viz_engine = create_engine(f'postgresql://{env_db_username}:{env_db_password}@{env_db_host}/{env_db_database}')
        now = datetime.now()
        formatted_date = now.strftime('%Y-%m-%d')
        formatted_now = now.strftime('%Y-%m-%d %H:%M:%S')
        total_secs = int(time_difference.total_seconds())

        data = {'model_name': [tracking_input_model_name],
                'method': [1],
                'session_date': [formatted_date],
                'session_time': [formatted_now],
                'skipped_count': [skipped_count],
                'process_count': [process_count],
                'error_location': [error_location],
                'duration': [total_secs],
                'mem_peak': [peak_memory]
                }

        # Create DataFrame
        df_tracker = pd.DataFrame(data)

        #df_tracker.to_postgis(con=viz_engine,schema=env_db_tracking_schema ,name=env_db_tracking_table_name , if_exists='append')
        df_tracker.to_sql(con=viz_engine,schema=env_db_tracking_schema ,name=env_db_tracking_table_name , index=False, if_exists='append')
    except:
        print("[track_changes] Error uploading summary to tracking table")

######################################################################################
## The Engine
######################################################################################

def lambda_handler(event, context):

    try:
        console_debugging = False #True #False #A way to show step messages within testing

        upload_tracking = True #Only use this for testing purposes

        if upload_tracking:
            tracemalloc.start()  #FOR TESTING ONLY

        ########################################################################################
        print("[Main start]")
        start_time = datetime.now()
        print(start_time.strftime("%Y-%m-%d %H:%M:%S")) # Output: 2025-02-03 16:40:01
        ########################################################################################

        if (console_debugging):
            print(event)

        #######################################################################################################################
        ## Step 0: Parse event arguments
        #######################################################################################################################
        ripple_file = ''
        input_flow_file = ''
        start_reaches_file = ''
        library_folder = ''
        output_fim_raster_file = ''
        output_vector_file = ''
        create_both_outputs = "FALSE" #Default value
        output_control_file = ''
        output_log_file = ''
        #verbose = "ERROR" #TODO Use when eventually in PROD environment
        verbose = "DEBUG"


        ####################################
        #Needed for batch jobs
        output_fim_raster_fname = "fim.tif"
        output_vector_fname = "fim.parquet"

        env_db_host = os.getenv('VIZ_DB_HOST')          #rds-viz.hydrovis.internal:5432
        env_db_username = os.getenv('VIZ_DB_USERNAME')  #viz_proc_admin_rw_user
        env_db_password = os.getenv('VIZ_DB_PASSWORD')  #
        env_db_database = os.getenv('VIZ_DB_DATABASE')  #vizprocessing
        env_SRID = os.getenv('VIZ_SRID')                #3857

        #TODO
        env_db_tracking_schema = "dev"
        env_db_tracking_table_name = "leonard_ripple_model_tracker"
        tracking_input_model_name = "LAMBDA_TEST"
        env_db_schema = "dev" #Using as my dummy for lambda tests
        env_db_tablename = "leonard_ripple_max_flows_ana" #Using as my dummy for lambda tests
        ####################################

        #Decision made to use control file only
        #A little confusing, but keeping code in place for now in case task changes.
        step3_only = True
        step3_only_Method1 = True   # This method to create the FIM with data we need will use the existing files
                                    # stored in the library extent folder
        #step3_only_Method2 = False  # TODO This method when implemented will use parquet files.
                                    # From early testing ran into memory usage issues and restrictions on file sizes
                                    # To meet deadline will focus on Method 1 first.

        argument_method_step = False #This means Lambda handle via Test i.e. Not a batch job
        try:
            dummy = event['arg_ripple_file']
            argument_method_step = False
        except KeyError:
            argument_method_step = True ##Assume this for now

        if argument_method_step == True:
            try:
                print("[Step Function 1]")

                #Values coming by csv row in a Map function
                #Decided to break apart in case we split buckets, folders etc.
                input_model_bucket = event['model_bucket']
                input_model_key = event['model_key']
                input_model_name = event['model_name']
                output_schema_table_name = event['destination_schema_table_name'] #output destination table
                input_flow_file = event['maxFlowTable']

                #TODO come back and evaluate if it still makes sense to break model s3 into parts
                #TODO error checking
                #arg_input_from_map = f"s3://{input_model_bucket}{input_model_key}{input_model_name}"
                arg_input_from_map = f"{input_model_bucket}{input_model_key}{input_model_name}"

                #arg_input_from_map = event['Model_FullPath']
                arg_input_folder_path_wo_s3 = arg_input_from_map.replace("s3://",'')

                ripple_file = f"{arg_input_from_map}ripple.gpkg"

                if (console_debugging): 
                    print(f"[Step:1] input_flow_file = {input_flow_file}")

                start_reaches_file = f"{arg_input_from_map}start_reaches.csv"

                if step3_only == False: #TRUE means we are using control file only False means creating FIM raster with Flows2Fim
                    library_folder = f"/vsis3/{arg_input_folder_path_wo_s3}library_extent" #Note use of vsis3 path for gdal
                if step3_only_Method1 == True: #TRUE means we are using control file with FIM tifs in library folder. False means Method2 with parquet files
                    library_folder = f"{arg_input_from_map}library_extent" #Note the use of S3 bucket

                create_both_outputs = "FALSE" #"TRUE" #"FALSE" #Default value

                #Destination provided in csv file
                input_table_split = output_schema_table_name.split('.')
                env_db_schema = input_table_split[0]
                env_db_tablename = input_table_split[1]

                tracking_input_model_name = input_model_name
    #rename these

            except Exception as e:
                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes( env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,9999,time_difference,peak_mem)

                traceback_str = traceback.format_exc()
                return {
                    'message': f"[Step:0-1-0] Argument missing errors. {event} --- {traceback_str}"
                }


        #Get values to be used by lambda function and do some basic checks
        if argument_method_step == False: #This means Lambda handle via Test i.e. Not a batch job
            try:
                ripple_file = event['arg_ripple_file']
            except KeyError:
                return {
                    'message': f"[Step:0-1-1] Ripple file argument missing. {event}"
                }

            try:
                input_flow_file = event['arg_flow_file']
            except KeyError:
                return {
                    'message': f"[Step:0-1-2] Flow file argument missing."
                }

            try:
                start_reaches_file = event['arg_start_reaches_file']
            except KeyError:
                return {
                    'message': f"[Step:0-1-3] Start Reaches file argument missing."
                }

            if step3_only_Method1 == True: #TRUE means we are using control file with FIM tifs in library folder. False means Method2 with parquet files
                try:
                    library_folder = event['arg_library_folder']
                except KeyError:
                    return {
                        'message': f"[Step:0-1-4] Library folder argument missing."
                    }

            if step3_only == False: #TRUE means we are using control file only False means creating FIM raster with Flows2Fim
                try:
                    output_fim_raster_file = event['arg_output_raster_file']
                except KeyError:
                    return {
                        'message': f"[Step:0-1-5] FIM Raster file argument missing."
                    }

                #Note: This argument IS NOT mandatory
                try:
                    output_vector_file = event['arg_output_vector_file']
                except KeyError:
                    print("[Step:0-1-6] WARNING: Missing vector file argument")

                try:
                    create_both_outputs = event['arg_create_both_outputs']
                except KeyError:
                    return {
                        'message': f"[Step:0-1-7] Missing create both outputs argument."
                    }

            #Note: Also this argument is mandatory as a Flows2Fim step, uploading the control file to S3 bucket IS NOT mandatory
            try:
                output_control_file = event['arg_output_control_file']
            except KeyError:
                print("[Step:0-1-8] WARNING: Missing control file argument")

            #Note: Uploading the log file to S3 bucket IS NOT mandatory
            try:
                output_log_file = event['arg_output_log_file']
            except KeyError:
                print("[Step:0-1-9] WARNING: Missing log file argument")

            #Note: Will use a default value instead of a user specified version.
            try:
                verbose = event['arg_verbose']
            except KeyError:
                print("[Step:0-1-10] WARNING: Missing verbose argument")
        else: #Check Batch variables needed
            if not check_environment_value(env_db_host):
                return {
                    'message': f"[Step:0-2-1] Invalid database host."
                }
            if not check_environment_value(env_db_username):
                return {
                    'message': f"[Step:0-2-2] Invalid database username."
                }
            if not check_environment_value(env_db_password):
                return {
                    'message': f"[Step:0-2-3] Invalid database password."
                }
            if not check_environment_value(env_db_database):
                return {
                    'message': f"[Step:0-2-4] Invalid database name."
                }
            if not check_environment_value(env_SRID):
                return {
                    'message': f"[Step:0-2-5] Invalid SRID value."
                }

        ########################################################################################
        # Common variables
        # These should rarely be modified. Keep in sync with Dockerfile.
        ########################################################################################
        if not os.path.exists("/tmp/data"):
            os.mkdir("/tmp/data")

        dir_data_inputs = "/tmp/data/inputs"
        dir_data_outputs = "/tmp/data/outputs"
        dir_logs = "/tmp/data/logs"
        dir_app = "/var/task"

        if os.path.exists(dir_data_inputs):
            shutil.rmtree(dir_data_inputs)
        if os.path.exists(dir_data_outputs):
            shutil.rmtree(dir_data_outputs)

        if not os.path.exists(dir_data_inputs):
            os.mkdir(dir_data_inputs)
        if not os.path.exists(dir_data_outputs):
            os.mkdir(dir_data_outputs)
        if not os.path.exists(dir_logs):
            os.mkdir(dir_logs)


        upload_chunksize = 4096 #Chunk size for uploading rows to database. ATM this is a guess, need some large datasets to evaluate MB usage
        env_PROJ_LIB = '/root/miniconda3/share/proj/'       #BEWARE when applying this variable as when gdal apps vs conda
        env_vector_python = '/root/miniconda3/bin/python3'  #This value needs to be the conda python env to meet ggdal/arrow requirements
        env_vector_gdal =  '/usr/bin/gdal_polygonize.py'    #Path to gdals python scripts
        #TODO Replace/remove above env variables with new conda env

        #######################################################################################################################
        ## Step 1: Set up logging
        ## Create and configure logger
        #######################################################################################################################
        if (console_debugging):
            print("[Step:1] Setting up logging")
        print("[Step:1] Setting up logging")

        #Default log file name
        log_file = "LOG_Flows2Fim"
        current_time = datetime.now().strftime("%H:%M:%S")
        if (console_debugging):
            print("Current time is:", current_time)
        print("Current time is:", current_time)

        log_filename_local = dir_logs + "/"+ log_file + "_" + current_time + ".log"
        logger.add(log_filename_local)

        #######################################################################################################################
        ## Step 2: Check user inputs
        #######################################################################################################################
        if (console_debugging):
            print("[Step:2A] Checking user inputs")

        logger.debug("[Step:2] Check user inputs")

        logger.debug(f"[Step:2-0-01] {ripple_file}")        #Step 3
        logger.debug(f"[Step:2-0-02] {input_flow_file}")    #Step 3
        logger.debug(f"[Step:2-0-03] {start_reaches_file}") #Step 3
        logger.debug(f"[Step:2-0-04] {library_folder}")     #Step 3 when method is to create FIM from library folder
        logger.debug(f"[Step:2-0-05] {output_fim_raster_file}")
        logger.debug(f"[Step:2-0-06] {output_vector_file}")
        logger.debug(f"[Step:2-0-07] {create_both_outputs}")
        logger.debug(f"[Step:2-0-08] {output_control_file}")
        logger.debug(f"[Step:2-0-09] {output_log_file}")
        logger.debug(f"[Step:2-0-10] {verbose}")

        logger.debug(f"[Step:2-0-11] {output_fim_raster_fname}")
        logger.debug(f"[Step:2-0-12] {output_vector_fname}")
        logger.debug(f"[Step:2-0-13] {env_db_host}")
        logger.debug(f"[Step:2-0-14] {env_db_username}")
        logger.debug(f"[Step:2-0-15] {env_db_password}")
        logger.debug(f"[Step:2-0-16] {env_db_database}")
        logger.debug(f"[Step:2-0-17] {env_db_schema}")
        logger.debug(f"[Step:2-0-18] {env_db_tablename}")
        logger.debug(f"[Step:2-0-19] {env_SRID}")

        ########################################################################################
        ## [2-1-2] Get Ripple file
        ########################################################################################
        logger.debug(f"[Step:2-1-2] Download Ripple file {ripple_file}")
        ripple_bucket, ripple_key, ripple_fname = parse_s3_url_GET_bucket_key_filename(ripple_file)
        if (console_debugging):
            print("Bucket:", ripple_bucket)
            print("Key:", ripple_key)
            print("Fname:", ripple_fname)

        ripple_local_path = os.path.join(dir_data_inputs, ripple_fname)

        try:
            s3.Bucket(ripple_bucket).download_file(ripple_key, ripple_local_path)
            logger.info( "Copied Ripple file to -> " + str(ripple_local_path))

        except botocore.exceptions.ClientError as e:
            if upload_tracking:
                end_time = datetime.now()
                time_difference = end_time - start_time
                current, peak = tracemalloc.get_traced_memory()
                peak_mem = peak / (1024 * 1024)
                track_changes(env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,212,time_difference,peak_mem)

            if e.response["Error"]["Code"] == "404":
                logger.critical(f"[Step:2-1-2] The key does not exist Key: '{ripple_bucket}'/'{ripple_key}' does not exist!")
                print(f"[Step:2-1-2] The key does not exist Key: '{ripple_bucket}'/'{ripple_key}' does not exist!")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2120,time_difference,peak_mem)

                sys.exit(2120)
            elif e.response["Error"]["Code"] == "403":
                logger.critical(f"[Step:2-1-2] Unauthorized, including invalid bucket Key: '{ripple_bucket}'/'{ripple_key}' does not exist!")
                print(f"[Step:2-1-2] Unauthorized, including invalid bucket Key: '{ripple_bucket}'/'{ripple_key}' does not exist!")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes( env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1, 2121,time_difference,peak_mem)

                sys.exit(2121)
            else:
                logger.critical(f"[Step:2-1-2] Something else went wrong with downloading '{ripple_file}'")
                print(f"[Step:2-1-2] Something else went wrong with downloading '{ripple_file}'")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password, env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1, -1,2122,time_difference,peak_mem)

                sys.exit(2122)
                raise


        ########################################################################################
        ## [2-1-3] Get flows.csv input
        ########################################################################################

        logger.debug(f"[Step:2-1-3] Download Ripple file {input_flow_file}")
        flow_bucket, flow_key, flow_fname = parse_s3_url_GET_bucket_key_filename(input_flow_file)
        if (console_debugging):
            print("Bucket:", flow_bucket)
            print("Key:", flow_key)
            print("Fname:", flow_fname)

        flow_local_path = os.path.join(dir_data_inputs, flow_fname)

        try:
            s3.Bucket(flow_bucket).download_file(flow_key, flow_local_path)
            logger.info( "Copied Flows file to -> " + str(ripple_local_path))

        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.critical(f"[Step:2-1-3] The key does not exist Key: '{flow_bucket}'/'{flow_key}' does not exist!")
                print(f"[Step:2-1-3] The key does not exist Key: '{flow_bucket}'/'{flow_key}' does not exist!")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2130, time_difference,peak_mem)

                sys.exit(2130)
            elif e.response["Error"]["Code"] == "403":
                logger.critical(f"[Step:2-1-3] Unauthorized, including invalid bucket Key: '{flow_bucket}'/'{flow_key}' does not exist!")
                print(f"[Step:2-1-3] Unauthorized, including invalid bucket Key: '{flow_bucket}'/'{flow_key}' does not exist!")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes( env_db_username, env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1, 2131,time_difference,peak_mem)

                sys.exit(2131)
            else:
                logger.critical(f"[Step:2-1-3] Something else went wrong with downloading '{input_flow_file}'")
                print(f"[Step:2-1-3] Something else went wrong with downloading '{input_flow_file}'")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes( env_db_username,env_db_password,env_db_host, env_db_database, env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2132,time_difference, peak_mem)

                sys.exit(2132)
                raise

        ########################################################################################
        ## [2-1-4] Get start_reaches_file.csv input
        ########################################################################################

        logger.debug(f"[Step:2-1-4] Download start reaches file {start_reaches_file}")
        start_reaches_bucket, start_reaches_key, start_reaches_fname = parse_s3_url_GET_bucket_key_filename(start_reaches_file)
        if (console_debugging):
            print("Bucket:", start_reaches_bucket)
            print("Key:", start_reaches_key)
            print("Fname:", start_reaches_fname)

        start_reaches_local_path = os.path.join(dir_data_inputs, start_reaches_fname)

        try:
            s3.Bucket(start_reaches_bucket).download_file(start_reaches_key, start_reaches_local_path)
            logger.info( "Copied Starts Reach file to -> " + str(start_reaches_local_path))

        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.critical(f"[Step:2-1-4]The key does not exist Key: '{start_reaches_bucket}'/'{start_reaches_key}' does not exist!")
                print(f"[Step:2-1-4]The key does not exist Key: '{start_reaches_bucket}'/'{start_reaches_key}' does not exist!")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes( env_db_username, env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2140,time_difference,peak_mem)

                sys.exit(2140)
            elif e.response["Error"]["Code"] == "403":
                logger.critical(f"[Step:2-1-4] Unauthorized, including invalid bucket Key: '{start_reaches_bucket}'/'{start_reaches_key}' does not exist!")
                print(f"[Step:2-1-4] Unauthorized, including invalid bucket Key: '{start_reaches_bucket}'/'{start_reaches_key}' does not exist!")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2141,time_difference,peak_mem)

                sys.exit(2141)
            else:
                logger.critical(f"[Step:2-1-4] Something else went wrong with downloading '{start_reaches_file}'")
                print(f"[Step:2-1-4] Something else went wrong with downloading '{start_reaches_file}'")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2142,time_difference,peak_mem)

                sys.exit(2142)
                raise

        ########################################################################################
        ## [2-1-5] Check library_folder input
        ## Some issues:
        ##             - How do we handle empty folders?
        ##             - How do we know if all the files are in the folder?
        ##             - For now assuming the folder contents are fine
        ##               - I would suggest having a script used by Rob to validate after downloading data
        ##               - Need a way to know what HUCs/Folders to skip over
        ########################################################################################
        #if step3_only == False: #TRUE means we are using control file only False means creating FIM raster with Flows2Fim
        if step3_only_Method1 == True: #TRUE means we are using control file with FIM tifs in library folder. False means Method2 with parquet files

            logger.debug(f"[Step:2-1-5] Checking library folder {library_folder}")

            library_folder_str = str(library_folder) #Lets force it to a string
            library_extent_folder = library_folder_str

            parsed_url = urlparse(library_folder_str)
            # Code will handle both s3 path and vsis3 paths
            if parsed_url.scheme == 's3':
                logger.debug(f"[Step:2-1-5] Parsing given s3 folder and making path to use GDAL's vsis3: {library_folder_str}")
                library_extent_folder = library_folder_str.replace("s3://", "/vsis3/")
                logger.debug(f"[Step:2-1-5] Path changed to use GDAL's vsis3: {library_extent_folder}")
            elif library_folder_str.startswith("/vsis3/"):
                logger.debug(f"[Step:2-1-5] Assuming provided vsis3 path is valid: {library_folder_str}")
                library_extent_folder = library_folder_str  #Assuming user input is valid
            else:
                logger.critical(f"[Step:2-1-5] Do not know how to handle given library folder path '{library_folder_str}'")
                print(f"[Step:2-3-5] Do not know how to handle given library folder path '{library_folder_str}'")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password,env_db_host, env_db_database,env_db_tracking_schema, env_db_tracking_table_name,tracking_input_model_name,-1, -1, 2150,time_difference,peak_mem)

                sys.exit(2150)
                raise

        #######################################################################################################################
        ## Handle Arguments for Outputs
        if (console_debugging):
            print("[Step:2B] Check output parameters")
        #######################################################################################################################
        logger.debug("[Step:2-2-1] Parsing S3 paths and uploading to s3 Bucket")

        ########################################################################################
        ## [2-2-2] Check output s3 folder path and filename for FIM RESULT
        ##
        ## Need to come back here and enforce naming patterns
        ##  * For example if + replaces spaces etc
        ########################################################################################
        if step3_only == False: #TRUE means we are using control file only False means creating FIM raster with Flows2Fim
            logger.debug(f"[Step:2-2-2] Checking Mandatory output fim file (*.tif) and folder S3 path {output_fim_raster_file}")

            #Handle one off Lambda tests versus batch jobs
            if argument_method_step == False: #This means Lambda handle via Test i.e. Not a batch job
                output_fim_raster_file_str = str(output_fim_raster_file)       #.replace(" ", "")       #Lets force it to a string and remove spaces

                if len(output_fim_raster_file_str) < 5:  #Likely a bad name specified (should end with .tif)
                    logger.critical(f"[Step:2-2-2] Given Mandatory tif file name is not valid '{output_fim_raster_file_str}'")
                    sys.exit(2220)
                    raise

                output_fim_raster_bucket, output_fim_raster_key, output_fim_raster_fname = parse_s3_url_GET_bucket_key_filename(output_fim_raster_file_str)
                if (console_debugging):
                    print("Bucket:", output_fim_raster_bucket)
                    print("Key:", output_fim_raster_key)
                    print("Fname:", output_fim_raster_fname)

                try:
                    extension = os.path.splitext(output_fim_raster_fname)[1]

                    #TODO add more options than just a cog tif
                    if extension != ".tif":
                        logger.critical(f"[Step:2-2-2] Given Mandatory FIM Raster tif file name is not valid. Missing extension. '{output_fim_raster_file_str}'")
                        sys.exit(2221)
                        raise

                except:
                        logger.critical(f"[Step:2-2-2] Given Mandatory FIM Raster tif file name is not valid. Error testing extension. '{output_fim_raster_file_str}'")
                        sys.exit(2222)
                        raise

            #This will be the output created locally. Then the given s3 name will be copied to designated output location (When specified)
            output_fim_raster_local_path = os.path.join(dir_data_outputs, output_fim_raster_fname)

        ########################################################################################
        ## [2-2-3] Check output s3 folder path and filename for OPTIONAL Vector RESULT
        ########################################################################################
        if step3_only == False: #TRUE means we are using control file only False means creating FIM raster with Flows2Fim
            logger.debug(f"[Step:2-2-3] Checking OPTIONAL output vector file and folder S3 path{output_vector_file}")

            output_vector_file_str = str(output_vector_file) #.replace(" ", "") #Lets force it to a string and remove spaces

            #Handle one off Lambda tests versus batch jobs
            if argument_method_step == False: #This means Lambda handle via Test i.e. Not a batch job
                vector_specified = False
                output_vector_local_path = ""

                if create_both_outputs.upper() == "TRUE":
                    vector_specified = True

                    if len(output_vector_file_str) < 9: #Likely a bad name specified (should end with .parquet)
                        logger.critical(f"[Step:2-2-3] Given vector file name is not valid '{output_vector_file_str}'")
                        sys.exit(2230)
                        raise

                    output_vector_bucket, output_vector_key, output_vector_fname = parse_s3_url_GET_bucket_key_filename(output_vector_file_str)
                    if (console_debugging):
                        print("Bucket:", output_vector_bucket)
                        print("Key:", output_vector_key)
                        print("Fname:", output_vector_fname)

                    try:
                        extension = os.path.splitext(output_vector_fname)[1]

                        if extension != ".parquet":
                            logger.critical(f"[Step:2-2-3] Given OPTIONAL parquet file name is not valid. Missing extension. '{output_vector_file_str}'")
                            sys.exit(2231)
                            raise

                    except:
                            logger.critical(f"[Step:2-2-3] Given OPTIONAL parquet file name is not valid. Error testing extension. '{output_vector_file_str}'")
                            sys.exit(2232)
                            raise

            #This will be the output created locally.
            output_vector_local_path = os.path.join(dir_data_outputs, output_vector_fname)

        ########################################################################################
        ## [2-2-4] Does the control file need to be uploaded?
        ##         * Default is to create log file locally and only upload the file to S3 path if user needs it. i.e. for testing
        ########################################################################################
        logger.debug(f"[Step:2-2-4] Checking control file settings")
        upload_control_file = False #Default value is no do not upload
        #Set default control output needed for step 2 of fims2flow.exe
        output_control_local_path = os.path.join(dir_data_outputs, "controls.csv")

        output_control_file_str = str(output_control_file) #User given name
        if len(output_control_file_str) < 5: #.csv Likely a bad control file name provided ignoring it. Will not raise an error on it.
            logger.info(f"[Step:2-2-4] Given control file name not valid. Control file will not upload to S3 bucket. '{output_control_file_str}'")
            upload_control_file = False #Refuse to upload file. Will use local value instead.
        else:
            upload_control_file = True

        if upload_control_file == True:
            #Note: these S3 Control variables are used to upload the control file. See Step 3.
            output_control_bucket, output_control_key, output_control_fname = parse_s3_url_GET_bucket_key_filename(output_control_file_str)
            if (console_debugging):
                print("Bucket:", output_control_bucket)
                print("Key:", output_control_key)
                print("Fname:", output_control_fname)

            try:
                extension = os.path.splitext(output_control_fname)[1]

                if extension != ".csv":
                    logger.critical(f"[Step:2-2-4] Given Mandatory csv file name is not valid. Missing extension. '{output_control_file_str}'")
                    sys.exit(2240)

                    if upload_tracking:
                        end_time = datetime.now()
                        time_difference = end_time - start_time
                        current, peak = tracemalloc.get_traced_memory()
                        peak_mem = peak / (1024 * 1024)
                        track_changes( env_db_username,env_db_password,env_db_host,env_db_database, env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,2241,time_difference,peak_mem)

                    raise

            except:
                    logger.critical(f"[Step:2-2-4] Given Mandatory tif file name is not valid. Error testing extension. '{output_control_file_str}'")
                    sys.exit(2241)
                    raise

            #This will be the output created locally. Then the given s3 name will be copied to designated output lcoation
            output_control_local_path = os.path.join(dir_data_outputs, output_control_fname)

        ########################################################################################
        ## [2-2-5] Does log file need to be uploaded?
        ##         * Default log name is always created, user provided name will be used in upload.
        ########################################################################################
        logger.debug(f"[Step:2-2-5] Checking log settings")
        upload_log_file = False #Default value is no do not upload

        output_log_file_str = str(output_log_file) #User given name
        if len(output_log_file_str) < 5: #.log Likely a bad log name provided ignoring it. But will not raise an error on it.
            logger.info(f"[Step:2-2-5] Given log file name not valid. Log file will not be upload to S3 bucket. '{output_log_file_str}'")
            upload_log_file = False #Refuse to upload file.
        else:
            upload_log_file = True #user wants to upload log file as well

        if upload_log_file == True:
            output_log_bucket, output_log_key, output_log_fname = parse_s3_url_GET_bucket_key_filename(output_log_file_str)
            if (console_debugging):
                print("Bucket:", output_log_bucket)
                print("Key:", output_log_key)
                print("Fname:", output_log_fname)

            try:
                extension = os.path.splitext(output_log_fname)[1]

                if extension != ".txt":
                    logger.critical(f"[Step:2-2-5] Given log file name is not valid. Missing extension. '{output_log_file_str}'")

                    if upload_tracking:
                        end_time = datetime.now()
                        time_difference = end_time - start_time
                        current, peak = tracemalloc.get_traced_memory()
                        peak_mem = peak / (1024 * 1024)
                        track_changes(env_db_username, env_db_password, env_db_host, env_db_database, env_db_tracking_schema, env_db_tracking_table_name, tracking_input_model_name,-1, -1, 2250, time_difference, peak_mem)

                    sys.exit(2250)

                    raise
            except:
                    logger.critical(f"[Step:2-2-5] Given log file name is not valid. Error testing extension. '{output_log_file_str}'")
                    
                    if upload_tracking:
                        end_time = datetime.now()
                        time_difference = end_time - start_time
                        current, peak = tracemalloc.get_traced_memory()
                        peak_mem = peak / (1024 * 1024)
                        track_changes(env_db_username, env_db_password, env_db_host, env_db_database, env_db_tracking_schema, env_db_tracking_table_name, tracking_input_model_name,-1, -1, 2251, time_difference, peak_mem)

                    sys.exit(2251)
                    raise

        #######################################################################################################################

        #######################################################################################################################
        ## Step 3: Execute Flows2Fim.exe Control file
        ##
        ## TODO: We need meaningful error codes from flows2fim.exe and parse these to end
        ## WARNING: For what ever reason(s) if uploading the control fails, the workflow will continue.
        ##          This decision is based on that the control file is not required anywhere else ATM.
        ##
        #######################################################################################################################
        if (console_debugging):
            print("[Step:3] Create Control file")
        logger.debug(f"[Step:3-0-1] Create Control file")

        command_line = str(dir_app) + "/flows2fim controls -db " + str(ripple_local_path) + " -f " + str(flow_local_path) + " -scsv " + str(start_reaches_local_path) + " -o " + str(output_control_local_path)
        ans = subprocess.run(command_line, shell=True)
        logger.debug(ans)

        if os.path.exists(str(output_control_local_path)):
            logger.debug(f"[Step:3-0-2] Control file created")
            file_size = os.path.getsize(str(output_control_local_path))
            logger.debug(f"[Step:3-0-3] Control file size {file_size}")

            #30 bytes is based on just a header returned. If no rows given unknown behavior expected.
            #For now, will cancel proceeding.
            #KEEP WANT TO SEE WHAT HAPPENS WITH mip_03150110
            if file_size < 30:
                logger.debug(f"[Step:3-0-4] Control file size created too small. '{file_size}' -> '{output_control_local_path}'")
                result = {
                    "statusCode": 200,  # Replace with the desired status code
                    "body": json.dumps(f"Flows2Fim.exe finished due to empty control file"),
                    "headers": {
                        "Content-Type": "application/json"
                    }
                }

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes( env_db_username, env_db_password, env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,304,time_difference, peak_mem)

                return result
                #sys.exit(3000)
                #raise
    #        #output_control_file

            #TODO Got this far, for now assuming control file is good w/o checking subprocess errors/warnings.
            if upload_control_file:
                logger.info(f"[Step:3-0-5] Attempting to upload Control file to S3 bucket")
                try:
                    s3_client = boto3.client('s3') #DOES IT HELP?
                    logger.critical(f"[Step:3-0-7] control '{output_control_bucket}'")
                    logger.critical(f"[Step:3-0-7] control '{output_control_key}'")

                    output_bucket_control_file = str(output_control_key)
                    with open(output_control_local_path, "rb") as f:
                        s3_client.upload_fileobj(f, output_control_bucket, output_bucket_control_file)
                except:
                    logger.critical(f"[Step:3-0-6] FAILED to upload local control file. '{output_control_local_path}'")
                    logger.critical(f"[Step:3-0-7] FAILED to upload control file to S3. '{output_control_bucket}'")
                    logger.critical(f"[Step:3-0-8] BEWARE Continuing the workflow.")
                    if upload_tracking:
                        end_time = datetime.now()
                        time_difference = end_time - start_time
                        current, peak = tracemalloc.get_traced_memory()
                        peak_mem = peak / (1024 * 1024)
                        track_changes(env_db_username,env_db_password, env_db_host, env_db_database, env_db_tracking_schema, env_db_tracking_table_name, tracking_input_model_name, -1, -1, 308, time_difference, peak_mem)
        else:
            logger.critical(f"[Step:3-0-9] ERROR during the process of creating the Control file (critical for this workflow). '{output_control_local_path}'")

            if upload_tracking:
                end_time = datetime.now()
                time_difference = end_time - start_time
                current, peak = tracemalloc.get_traced_memory()
                peak_mem = peak / (1024 * 1024)
                track_changes( env_db_username, env_db_password, env_db_host, env_db_database, env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1, 3001,time_difference,peak_mem)

            sys.exit(3001)
            raise

        #######################################################################################################################
        ## Step 3B: Create FIM Vector results from Control File
        ##
        #######################################################################################################################
        #TRUE means we are using control file with FIM tifs in library folder. False means Method2 with parquet files
        if step3_only_Method1 == True:

            #File to read is output_control_local_path
            #Header is reach_id,flow,control_stage

            #Concept is load each row, get the tif file, convert the tif to a vector file, insert into a parquet file.
            #Then upload the parquet file to database and/or S3 bucket
            #The code below ATM uploads the vector per row to the database. I was getting weird concat issues.
            #TODO to meet the deadline, potential improvements include uploading larger chunks

            # Problems include: Running out of time. Amount of memory required.

            #Test used for test
            #s3_path = "s3://hv-vpp-dev-ripple/input/ngwpc_data/30_pcnt_domain/ble_12030106_EastForkTrinity/library_extent/"

            s3_client = boto3.client('s3') #DOES IT HELP?

            s3_path = library_folder #Beware not using the same logic as Step4 here (replace s3 with vsis3)

            if s3_path.startswith("/vsis3/"):
                s3_path = s3_path.replace("/vsis3/", "s3://")

            #s3_path = library_folder_str
            library_bucket, library_key, library_fname = parse_s3_url_GET_bucket_key_filename(s3_path)
            if (console_debugging):
                print("Bucket:", library_bucket)
                print("Key:", library_key)
                print("Fname:", library_fname) #Will be empty

            #file_path_list = []
            logger.debug(f"[Step:3-1-1] Opening Control File {output_control_local_path}")

            master_gdf = None
            file_cnt = 0
            error_cnt = 0
            skipped_cnt = 0

            with open(output_control_local_path, 'r') as c_file:
                next(c_file) #Skip Header
                for line in c_file:
                    logger.debug(f"[Step:3-XX] {line}")
                    split_line = line.split(',')
                    cf_reach_id = split_line[0].rstrip()
                    cf_flow = split_line[1].rstrip()
                    cf_control_stage = split_line[2].rstrip()

                    tmp_control_stage = str(cf_control_stage)

                    try:
                        tmp_int = int(cf_control_stage)
                        tmp_control_stage = str(tmp_int)
                        tmp_control_stage += "_0"
                    except:
                        try:
                            tmp_float = float(cf_control_stage)
                            tmp_floor = math.floor(tmp_float)
                            tmp_control_stage = str(tmp_floor)

                            if tmp_float % 1 == 0.5: #math.isclose(tmp_float, 0.5):
                                tmp_control_stage += "_5"
                            else:
                                tmp_control_stage += "_0"  #Potential logic issue here if intervals change
                        except:
                            tmp_control_stage = str(cf_control_stage) #Should be nd

                    #full_s3_raster_path = s3_path + cf_reach_id + "/z_" + tmp_control_stage + "/f_" + cf_flow + ".tif"
                    full_s3_raster_path = s3_path + "/" + cf_reach_id + "/z_" + tmp_control_stage + "/f_" + cf_flow + ".tif"
                    key_file_check = library_key + "/" + cf_reach_id + "/z_" + tmp_control_stage + "/f_" + cf_flow + ".tif"
                    #logger.debug(f"{full_s3_raster_path}")
                    if (console_debugging):
                        logger.debug(f"{key_file_check}")
                    #Continue if path exists
                    #Not all the paths exists!!!!

                    logger.debug(f"[Step:3-YY] {key_file_check}")
                    logger.debug(f"[Step:3-YY] {full_s3_raster_path}")

                    try:

                        #Check if file exists w/o downloading the file
                        s3_client.head_object(Bucket=library_bucket, Key=key_file_check)

                        try:
                            master_gdf = raster_to_geoparquet(full_s3_raster_path, cf_reach_id, cf_control_stage, cf_flow )
                            srid_as_int = 3857
                            try:
                                srid_as_int = int(env_SRID)
                            except:
                                srid_as_int = 3857
                                logger.debug(f"[Step:3-1-4] WARNING use default SRID value of {srid_as_int}")

                            df_prj = master_gdf.to_crs(epsg=srid_as_int)
                            if (console_debugging):
                                print("Reprojected CRS:", df_prj.crs)

                            #df_prj.set_crs('epsg:3857', inplace=True, allow_override=True)
                            df_prj.set_crs(f'epsg:{env_SRID}', inplace=True, allow_override=True)
                            df_prj.rename_geometry('geom', inplace=True)
                            df_prj.columns = df_prj.columns.str.lower()

                            viz_engine = create_engine(f'postgresql://{env_db_username}:{env_db_password}@{env_db_host}/{env_db_database}')

                            #if upload_chunksize < 512:
                            #    upload_chunksize = 512

                            if (console_debugging):
                                logger.debug(f"[Step:3-1-6] Using a chunk size of {upload_chunksize}")
                                logger.debug(f"[Step:3-1-6] Using {env_db_host} {env_db_database} {env_db_schema} {env_db_tablename}")

                            try:
                                #NOTE the use of append, as the step function will create the destination table before executing this image
                                #df_prj.to_postgis(con=viz_engine,schema=env_db_schema,name=env_db_tablename, if_exists='append', chunksize=upload_chunksize)
                                df_prj.to_postgis(con=viz_engine,schema=env_db_schema,name=env_db_tablename, if_exists='append')
                            except Exception as e:
                                traceback_str = traceback.format_exc()
                                logger.debug(f"[Step:3-1-2] failed to upload vector result to database")
                                logger.debug(f"{traceback_str} ")

                            file_cnt += 1
                        except:
                            logger.debug(f"[Step:3-1-3] Error with file {full_s3_raster_path}")
                            traceback_str = traceback.format_exc()
                            logger.debug(f"{traceback_str}")
                            error_cnt += 1
                    except:
                        #We know files are missing
                        if (console_debugging):
                            print("[Step:3-1-4] File does not exist:", full_s3_raster_path)
                            traceback_str = traceback.format_exc()
                            logger.debug(f"{traceback_str}")
                        skipped_cnt += 1

            logger.debug(f"[Step:3-1-5] Number of files processed {file_cnt} {error_cnt} {skipped_cnt} ")

            if upload_tracking:
                end_time = datetime.now()
                time_difference = end_time - start_time
                current, peak = tracemalloc.get_traced_memory()
                peak_mem = peak / (1024 * 1024)
                track_changes( env_db_username, env_db_password, env_db_host, env_db_database,env_db_tracking_schema, env_db_tracking_table_name,tracking_input_model_name,skipped_cnt,file_cnt,-1,time_difference, peak_mem)

        # This method usses the Second Step of Flows2Fim.
        # However we also need the stage values not currently generated.
        if step3_only == False: #TRUE means we are using control file only False means creating FIM raster with Flows2Fim
            #######################################################################################################################
            ## Step 4: Execute Flows2Fim.exe FIM file
            ##
            ## TODO: We need meaningful error codes from flows2fim.exe and parse these to end
            ##       Need to have output options added here as well (For now its cog tif)
            ##
            #######################################################################################################################
            if (console_debugging):
                print("[Step:4] Create FIM raster (cog tif) file")
            logger.debug(f"[Step:4-0-1] Create FIM cog tif file")

            fim_command_line = str(dir_app) + "/flows2fim fim -lib " + str(library_extent_folder) + " -c " + output_control_local_path + " -fmt cog -o " + str(output_fim_raster_local_path)
            fim_ans = subprocess.run(fim_command_line, shell=True)
            logger.debug(fim_ans)

            #Handle one off Lambda tests versus batch jobs
            if argument_method_step == False: #This means Lambda handle via Test i.e. Not a batch job
                if os.path.exists(str(output_fim_raster_local_path)):
                    logger.debug(f"[Step:4-0-2] FIM raster file created")
                    file_size = os.path.getsize(str(output_fim_raster_local_path))
                    logger.debug(f"[Step:4-0-3] FIM raster file size {file_size}")

                    #TODO Can we measure the size of a bad tif?
                    #TODO How to handle empty results

                    #TODO Got this far, for now assuming FIM file is good w/o checking subprocess errors/warnings.
                    logger.info(f"[Step:4-0-4] Attempting to upload FIM raster file to S3 bucket")
                    try:
                        s3_client = boto3.client('s3') #DOES IT HELP?

                        output_bucket_fim_raster_file = str(output_fim_raster_key)
                        with open(output_fim_raster_local_path, "rb") as f:
                            s3_client.upload_fileobj(f, output_fim_raster_bucket, output_bucket_fim_raster_file)
                    except:
                        logger.error(f"[Step:4-0-5] FAILED to upload local FIM raster file. '{output_fim_raster_local_path}'")
                        logger.error(f"[Step:4-0-6] FAILED to upload FIM raster file to S3. '{output_fim_raster_bucket}'")
                        sys.exit(4000)
                        raise

                else:
                    logger.critical(f"[Step:4-0-7] ERROR during the process of creating the FIM cog tif file (critical for this workflow). '{output_fim_raster_local_path}'")
                    sys.exit(4001)
                    raise


            #######################################################################################################################
            ## Step 5: Create Vector file from FIM Raster result
            ##
            ## TODO: We need file type options
            ##       Different ways to create the vectors
            ##       Handle errors
            ##
            #######################################################################################################################
            if (console_debugging):
                print("[Step:5] Create FIM Vector file")
            logger.debug(f"[Step:5-0-1] Create FIM Vector file")

            # Adding the environment here, as during testing of getting the proj folder correct
            # I observed Step4 reporting hundreds of warning projection errors.
            os.environ['PROJ_LIB'] = env_PROJ_LIB
            vector_command_line = ''

            #This uses more memory so will test w/o as the postgis errors are misleading and the issues reported are really permissions
            if False:
                print("[Step:5-0-2] Create FIM Vector file")
                logger.debug(f"[Step:5-0-2] Create FIM Vector file")

                output_prj_fim_raster_local_path = os.path.join(dir_data_outputs, "reproj.tif")
                #reprj_command_line = "/usr/bin/gdalwarp -t_srs 'epsg:3857' " + str(output_fim_raster_local_path) + " " + output_prj_fim_raster_local_path
                reprj_command_line = f"/usr/bin/gdalwarp -t_srs 'epsg:{env_SRID}' " + str(output_fim_raster_local_path) + " " + output_prj_fim_raster_local_path
                print(reprj_command_line)
                reproj_ans = subprocess.run(reprj_command_line, shell=True)
                logger.debug(reproj_ans)

                vector_command_line = env_vector_python + ' ' + env_vector_gdal + ' ' + str(output_prj_fim_raster_local_path) + ' -b 1 -f "Parquet" ' + str(output_vector_local_path) + ' OUTPUT DN'
            else:
                vector_command_line = env_vector_python + ' ' + env_vector_gdal + ' ' + str(output_fim_raster_local_path) + ' -b 1 -f "Parquet" ' + str(output_vector_local_path) + ' OUTPUT DN'

            logger.debug(vector_command_line)
            vector_ans = subprocess.run(vector_command_line, shell=True)
            logger.debug(vector_ans)

            #Handle one off Lambda tests versus batch jobs
            if argument_method_step == False: #This means Lambda handle via Test i.e. Not a batch job
                if vector_specified == True:
                    if os.path.exists(str(output_vector_local_path)):
                        logger.debug(f"[Step:5-0-3] FIM Vector file created")
                        file_size = os.path.getsize(str(output_vector_local_path))
                        logger.debug(f"[Step:5-0-4] FIM Vector file size {file_size}")

                        #TODO Measure the size of a bad vector?
                        #TODO How to handle empty results

                        logger.info(f"[Step:5-0-5] Attempting to upload FIM Vector file to S3 bucket")
                        try:
                            s3_client = boto3.client('s3') #DOES IT HELP?

                            output_bucket_vector_file = str(output_vector_key) #+ str(output_vector_fname)
                            with open(output_vector_local_path, "rb") as f:
                                s3_client.upload_fileobj(f, output_vector_bucket, output_bucket_vector_file)
                        except:
                            logger.error(f"[Step:5-0-6] FAILED to upload local FIM Vector file. '{output_vector_local_path}'")
                            logger.error(f"[Step:5-0-7] FAILED to upload FIM Vector file to S3. '{output_vector_bucket}'")
                            sys.exit(5000)
                            raise
                    else:
                        logger.critical(f"[Step:5-0-8] ERROR during the process of creating the FIM Vector file. '{output_vector_local_path}'")
                        sys.exit(5001)
                        raise
                else:
                    logger.debug(f"[Step:5-0-9] Not uploading FIM Vector file")


            #######################################################################################################################
            ## Step 6: Upload Vector file to database
            #######################################################################################################################
            if (console_debugging):
                print("[Step:6] Upload Vector file to Database")
            logger.debug(f"[Step:6-0-1] Upload FIM Vector file to Database")

            #Hack for testing
            if False: #argument_method_step == True:  #Using batch job to upload results to database
                logger.debug(f"[Step:6-0-2] Upload FIM Vector file to Database")

                df = geopandas.read_parquet(output_vector_local_path)
                #df = geopandas.read_file(output_vector_local_path, layer="silly")
                #df = geopandas.read_file(output_vector_local_path, geom_col="geom")

                # Check the current CRS
                if (console_debugging):
                    print("Original CRS:", df.crs)
                    print("Columns:", str(df.columns))

                tmp_len = len(df)
                logger.debug(f"[Step:6-0-3] Row count = {tmp_len}")

                srid_as_int = 3857
                try:
                    srid_as_int = int(env_SRID)
                except:
                    srid_as_int = 3857
                    logger.debug(f"[Step:6-0-4] WARNING use default SRID value of {srid_as_int}")


                df_prj = df.to_crs(epsg=srid_as_int)
                if (console_debugging):
                    print("Reprojected CRS:", df_prj.crs)

                #df_prj.set_crs('epsg:3857', inplace=True, allow_override=True)
                df_prj.set_crs(f'epsg:{env_SRID}', inplace=True, allow_override=True)
                df_prj.rename_geometry('geom', inplace=True)
                df_prj.columns = df_prj.columns.str.lower()

                df_prj = df_prj[df_prj['dn'] == 1]
                tmp_len2 = len(df_prj)
                logger.debug(f"[Step:6-0-5] Filtered (ignoring non 1 values) Row count = {tmp_len2}")

                viz_engine = create_engine(f'postgresql://{env_db_username}:{env_db_password}@{env_db_host}/{env_db_database}')

                if upload_chunksize < 512:
                    upload_chunksize = 512

                logger.debug(f"[Step:6-0-6] Using a chunk size of {upload_chunksize}")

                #NOTE the use of append, as the step function will create the destination table before executing this image
                df_prj.to_postgis(con=viz_engine,schema=env_db_schema,name=env_db_tablename, if_exists='append', chunksize=upload_chunksize)

                logger.debug(f"[Step:6-0-7] Uploaded dataframe to postgis {env_db_schema}.{env_db_tablename}")

            else:
                logger.debug(f"[Step:6-0-8] Not uploading FIM Vector file to Database")

        #######################################################################################################################
        ## Step 7: Upload log file to S3 bucket
        ##
        #######################################################################################################################
        if (console_debugging):
            print("[Step:7] Upload log file to S3 bucket")
        logger.debug(f"[Step:7-0-1] Upload log file to S3 bucket")

        if upload_log_file == True:
            logger.debug(f"[Step:7-0-2] Upload log file to S3 bucket")

            end_time = datetime.now()
            time_difference = end_time - start_time
            logger.debug( str(end_time.strftime("%Y-%m-%d %H:%M:%S"))) # Output: 2025-02-03 16:40:01
            logger.debug(f"Time difference: '{time_difference}'")

            logger.info(f"[Step:7-0-3] Attempting to upload log file to S3 bucket")
            try:
                if os.path.exists(str(log_filename_local)):
                    output_bucket_log_file = str(output_log_key) # + str(output_log_fname)

                    with open(log_filename_local, "rb") as f:
                        s3_client.upload_fileobj(f, output_log_bucket, output_bucket_log_file)

                    print(f"[Step:7-0-4] Uploaded local log file. '{log_filename_local}'")

            except:
                print(f"[Step:7-0-5] FAILED to upload local log file. '{log_filename_local}'")
                print(f"[Step:7-0-6] FAILED to upload log file to S3. '{output_log_bucket}'")
                print(f"[Step:7-0-7] FAILED to upload log file to S3. '{output_log_key}'")

                if upload_tracking:
                    end_time = datetime.now()
                    time_difference = end_time - start_time
                    current, peak = tracemalloc.get_traced_memory()
                    peak_mem = peak / (1024 * 1024)
                    track_changes(env_db_username,env_db_password,env_db_host,env_db_database,env_db_tracking_schema,env_db_tracking_table_name,tracking_input_model_name,-1,-1,7000,time_difference,peak_mem)

                sys.exit(7000)
                raise
        else:
            logger.debug(f"[Step:7-0-8] Not uploading log file to S3 bucket")

        ########################################################################################
        ## Wrap up
        ########################################################################################
        end_time = datetime.now()
        time_difference = end_time - start_time
        print(end_time.strftime("%Y-%m-%d %H:%M:%S")) 

        print("Time difference:", time_difference)
        print("[Main end]")

        if upload_tracking:
            tracemalloc.stop()

        result = {
            "statusCode": 200,  # Replace with the desired status code
            "body": json.dumps(f"Flows2Fim.exe container image finished in '{time_difference.total_seconds()}' seconds."),
            "headers": {
                "Content-Type": "application/json"
            }
        }
        return result

    #######################################################################################################################

    except Exception as e:
        traceback_str = traceback.format_exc()
        return {
            'message': f"Stack trace errors. {event} --- {traceback_str}"
        }        
