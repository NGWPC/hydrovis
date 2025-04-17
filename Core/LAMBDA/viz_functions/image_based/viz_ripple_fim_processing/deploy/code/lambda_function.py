import sys
import fsspec
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

from rasterio import features

import tracemalloc

#from osgeo import gdal
#print(gdal.__version__)

######################################################################################
START_TIME = datetime.now()

FS_S3 = fsspec.filesystem('s3')

ENV_DB_HOST = os.getenv('VIZ_DB_HOST')          #rds-viz.hydrovis.internal:5432
ENV_DB_USERNAME = os.getenv('VIZ_DB_USERNAME')  #
ENV_DB_PASSWORD = os.getenv('VIZ_DB_PASSWORD')  #
ENV_DB_DATABASE = os.getenv('VIZ_DB_DATABASE')  #vizprocessing
ENV_DB_SRID = os.getenv('VIZ_SRID')             #3857
VIZ_ENGINE = create_engine(f'postgresql://{ENV_DB_USERNAME}:{ENV_DB_PASSWORD}@{ENV_DB_HOST}/{ENV_DB_DATABASE}')
RIPPLE_LOCAL_PATH = ""        #Modified in get_Ripple_file function
FLOW_LOCAL_PATH = ""          #Modified in get_Flows_file function
START_REACHES_LOCAL_PATH = "" #Modified in get_Reaches_file function
ENV_DB_TRACKING_SCHEMA = "dev"
ENV_DB_TRACKING_TABLE_NAME = "leonard_ripple_model_tracker"
TRACKING_INPUT_MODEL_NAME = "LAMBDA_TEST"  #Modified in Step 0

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

def check_environment_value(variable):
    """
    Checks if the variable is a valid string.

    Parameters:
        variable: value to parse.

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

def raster_to_database(raster_path, input_fid, input_stage, input_extent):

    with rasterio.open(raster_path) as src:
        band = src.read(1)
        #mask = band != src.nodata
        #mask = band != 0
        values_to_mask = [1] #1 is the value we want to keep
        raster_data = src.read(1)
        mask = np.isin(raster_data, values_to_mask)

        shapes = rasterio.features.shapes(band, mask=mask, transform=src.transform)

        polygons = []
        values = []
        for geom, val in shapes:
            polygons.append(Polygon(geom['coordinates'][0]))
            values.append(val)

        gdf = gpd.GeoDataFrame({'feature_id': input_fid, 'stage_ft': input_stage, 'discharge_cfs': input_extent , 'geometry': polygons}, crs=src.crs)
        
        # Dissolve all geometries into one
        dissolved_gdf = gdf.dissolve(by='feature_id')
        dissolved_gdf = dissolved_gdf.reset_index()
        dissolved_gdf = dissolved_gdf.rename(columns={"index": "feature_id"})

        return dissolved_gdf

def track_changes( skipped_count, process_count, error_location):

    try:
        end_time = datetime.now()
        time_difference = end_time - START_TIME
        current, peak = tracemalloc.get_traced_memory()
        peak_memory = peak / (1024 * 1024)

        now = datetime.now()
        formatted_date = now.strftime('%Y-%m-%d')
        formatted_now = now.strftime('%Y-%m-%d %H:%M:%S')
        total_secs = int(time_difference.total_seconds())

        data = {'model_name': [TRACKING_INPUT_MODEL_NAME],
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
        df_tracker.to_sql(con=VIZ_ENGINE,schema=ENV_DB_TRACKING_SCHEMA, name=ENV_DB_TRACKING_TABLE_NAME, index=False, if_exists='append')
    except:
        print("[track_changes] Error uploading summary to tracking table")

def get_Ripple_file(ripple_file, dir_data_inputs,console_debugging ):
    
    ripple_bucket, ripple_key, ripple_fname = parse_s3_url_GET_bucket_key_filename(ripple_file)

    if (console_debugging):
        print("Bucket:", ripple_bucket)
        print("Key:", ripple_key)
        print("Fname:", ripple_fname)

    global RIPPLE_LOCAL_PATH
    RIPPLE_LOCAL_PATH = os.path.join(dir_data_inputs, ripple_fname)

    try:
        FS_S3.download( f"{ripple_file}", RIPPLE_LOCAL_PATH)
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"{traceback_str} ")
        return False
    
    if not os.path.exists(RIPPLE_LOCAL_PATH):
        print(f"Could not find local ripple file => {RIPPLE_LOCAL_PATH}")
        return False

    file_size = os.path.getsize(RIPPLE_LOCAL_PATH)
    if file_size < 30: #Just a header?
        print(f"Local ripple file size too small => {RIPPLE_LOCAL_PATH}")
        return False
    
    return True

def get_Flows_file(input_flow_file, dir_data_inputs,console_debugging ):
        
    flow_bucket, flow_key, flow_fname = parse_s3_url_GET_bucket_key_filename(input_flow_file)
    if (console_debugging):
        print("Bucket:", flow_bucket)
        print("Key:", flow_key)
        print("Fname:", flow_fname)

    global FLOW_LOCAL_PATH
    FLOW_LOCAL_PATH = os.path.join(dir_data_inputs, flow_fname)

    try:
        FS_S3.download( f"{flow_bucket}/{flow_key}", FLOW_LOCAL_PATH)
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"{traceback_str} ")
        return False
    
    if not os.path.exists(FLOW_LOCAL_PATH):
        print(f"Could not find local flow file => {FLOW_LOCAL_PATH}")
        return False
    
    file_size = os.path.getsize(FLOW_LOCAL_PATH)
    if file_size < 30: #Just a header?
        print(f"Local flow file size too small => {FLOW_LOCAL_PATH}")
        return False
            
    return True

def get_Reaches_file(start_reaches_file, dir_data_inputs,console_debugging ):

    start_reaches_bucket, start_reaches_key, start_reaches_fname = parse_s3_url_GET_bucket_key_filename(start_reaches_file)
    if (console_debugging):
        print("Bucket:", start_reaches_bucket)
        print("Key:", start_reaches_key)
        print("Fname:", start_reaches_fname)

    global START_REACHES_LOCAL_PATH
    START_REACHES_LOCAL_PATH = os.path.join(dir_data_inputs, start_reaches_fname)

    try:
        FS_S3.download( f"{start_reaches_file}", START_REACHES_LOCAL_PATH)
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"{traceback_str} ")
        return False
    
    if not os.path.exists(START_REACHES_LOCAL_PATH):
        print(f"Could not find local reaches file => {START_REACHES_LOCAL_PATH}")
        return False
    
    file_size = os.path.getsize(START_REACHES_LOCAL_PATH)
    if file_size <= 0: #Just a header? Some reaches are really small, for now just checking if zero
        print(f"Local reaches file size too small => {START_REACHES_LOCAL_PATH}")
        return False
                    
    return True

def get_all_data_inputs(ripple_file, input_flow_file, start_reaches_file, dir_data_inputs,console_debugging):

    try:

        download_result = get_Ripple_file(ripple_file, dir_data_inputs, console_debugging )
        if download_result == False:
            return False
        
        download_result = get_Flows_file(input_flow_file, dir_data_inputs, console_debugging )
        if download_result == False:
            return False
        
        download_result = get_Reaches_file(start_reaches_file, dir_data_inputs, console_debugging )
        if download_result == False:
            return False
        
        return True

    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"{traceback_str} ")        
        return False

def process_control_file_upload_to_database(s3_library_folder,         #Base S3 folder of HUC with FIM tifs
                                            output_control_local_path, #Control file created from Step 3
                                            env_db_schema,             #Schema of database destination
                                            env_db_tablename,          #Table Name of database destination
                                            console_debugging,         #For debugging purposes
                                            upload_tracking ):         #Upload number of tifs processed to table
    try:
        #Chunk size for uploading rows to database. ATM this is a guess, need some large datasets to evaluate MB usage
        upload_chunksize = 4096 

        #Concept is load each row, get the tif file, convert the tif to a vector file, insert into database.
        s3_path = s3_library_folder #Beware not using the same logic as Step4 here (replace s3 with vsis3)

        if s3_path.startswith("/vsis3/"):
            s3_path = s3_path.replace("/vsis3/", "s3://")

        library_bucket, library_key, library_fname = parse_s3_url_GET_bucket_key_filename(s3_path)
        if (console_debugging):
            print("Bucket:", library_bucket)
            print("Key:", library_key)
            print("Fname:", library_fname) #Will be empty

        logger.debug(f"[Step:4] Opening Control File {output_control_local_path}")

        master_gdf = None
        file_cnt = 0
        error_cnt = 0
        skipped_cnt = 0

        with open(output_control_local_path, 'r') as c_file:
            next(c_file) #Skip Header
            for line in c_file:
                
                if (console_debugging):
                    logger.debug(f"[Step:4-0-01] {line}")
                
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

                full_s3_raster_path = s3_path + "/" + cf_reach_id + "/z_" + tmp_control_stage + "/f_" + cf_flow + ".tif"
                key_file_check = library_key + "/" + cf_reach_id + "/z_" + tmp_control_stage + "/f_" + cf_flow + ".tif"

                #Continue if path exists
                #Not all the paths exists!!!!
                if (console_debugging):
                    logger.debug(f"[Step:4-0-02] {key_file_check}")
                    logger.debug(f"[Step:4-0-03] {key_file_check}")
                    logger.debug(f"[Step:4-0-04] {full_s3_raster_path}")

                try:

                    try:
                        master_gdf = raster_to_database(full_s3_raster_path, cf_reach_id, cf_control_stage, cf_flow )
                        srid_as_int = 3857
                        try:
                            srid_as_int = int(ENV_DB_SRID)
                        except:
                            srid_as_int = 3857
                            logger.debug(f"[Step:4-1-00] WARNING use default SRID value of {srid_as_int}")

                        df_prj = master_gdf.to_crs(epsg=srid_as_int)
                        if (console_debugging):
                            print("Reprojected CRS:", df_prj.crs)

                        df_prj.set_crs(f'epsg:{ENV_DB_SRID}', inplace=True, allow_override=True)
                        df_prj.rename_geometry('geom', inplace=True)
                        df_prj.columns = df_prj.columns.str.lower()

                        #if upload_chunksize < 512:
                        #    upload_chunksize = 512

                        if (console_debugging):
                            logger.debug(f"[Step:4-2-00] Using a chunk size of {upload_chunksize}")
                            logger.debug(f"[Step:4-2-01] Using {ENV_DB_HOST} {ENV_DB_DATABASE} {env_db_schema} {env_db_tablename}")

                        try:
                            #NOTE the use of append, as the step function will create the destination table before executing this image
                            #df_prj.to_postgis(con=viz_engine,schema=env_db_schema,name=env_db_tablename, if_exists='append', chunksize=upload_chunksize)
                            df_prj.to_postgis(con=VIZ_ENGINE,schema=env_db_schema,name=env_db_tablename, if_exists='append')
                        except Exception as e:
                            traceback_str = traceback.format_exc()
                            logger.debug(f"[Step:4-2-02] failed to upload vector result to database")
                            logger.debug(f"{traceback_str} ")

                        file_cnt += 1
                    except:
                        logger.debug(f"[Step:4-3-01] Error with file {full_s3_raster_path}")
                        traceback_str = traceback.format_exc()
                        logger.debug(f"{traceback_str}")
                        error_cnt += 1
                except:
                    #We know files are missing
                    if (console_debugging):
                        print("[Step:4-4-00] File does not exist:", full_s3_raster_path)
                        traceback_str = traceback.format_exc()
                        logger.debug(f"{traceback_str}")
                    skipped_cnt += 1

        logger.debug(f"[Step:4-5-00] Number of files processed {file_cnt} {error_cnt} {skipped_cnt} ")

        if upload_tracking:
            track_changes( skipped_cnt,file_cnt,-1)

    except Exception as e:
        if upload_tracking:
            track_changes( skipped_cnt,file_cnt, 9999)
        traceback_str = traceback.format_exc()
        print(f"{traceback_str} ")        
        return False

######################################################################################
## The Engine
######################################################################################

def lambda_handler(event, context):

    try:
        #Change these three boolean variables to reflect the environment.
        console_debugging = True #False #A way to show step messages within testing

        console_debugging_for_every_tif = False #Separated from console debugging due to large number of tifs
        upload_tracking = True #Only use this for testing purposes

        if upload_tracking == True: #FOR TESTING ONLY
            tracemalloc.start()  

        ########################################################################################
        print("[Ripple Main start]")
        print(START_TIME.strftime("%Y-%m-%d %H:%M:%S")) 
        ########################################################################################

        if console_debugging == True:
            print(event)

        ########################################################################################
        ## Step 0: Parse event arguments
        ########################################################################################
        ripple_file = ''
        input_flow_file = ''
        start_reaches_file = ''
        library_folder = ''

        ####################################
        env_db_schema = "dev" #Using as my dummy for lambda tests
        env_db_tablename = "leonard_ripple_max_flows_ana" #Using as my dummy for lambda tests
        ####################################

        try:
            if console_debugging == True:
                print("[Step:1 Prepare variables]")

            #Values coming by csv row in a Map function
            #Decided to break apart in case we split buckets, folders etc.
            input_model_bucket = event['model_bucket']
            input_model_key = event['model_key']
            input_model_name = event['model_name']
            output_schema_table_name = event['destination_schema_table_name'] #output destination table
            input_flow_file = event['maxFlowTable']

            arg_input_from_map = f"{input_model_bucket}{input_model_key}{input_model_name}"
            ripple_file = f"{arg_input_from_map}ripple.gpkg"
            start_reaches_file = f"{arg_input_from_map}start_reaches.csv"
            library_folder = f"{arg_input_from_map}library_extent" #Note the use of S3 bucket

            #Destination provided in csv file
            input_table_split = output_schema_table_name.split('.')
            env_db_schema = input_table_split[0]
            env_db_tablename = input_table_split[1]

            global TRACKING_INPUT_MODEL_NAME
            TRACKING_INPUT_MODEL_NAME = input_model_name

        except Exception as e:
            if upload_tracking:
                track_changes(-1,-1,7777)

            traceback_str = traceback.format_exc()
            raise Exception(f"[Step:0-0-00] Missing Arguments. {event} --- {traceback_str}")
        
        #Check Batch variables needed
        if not check_environment_value(ENV_DB_HOST):
            raise Exception(f"[Step:0-0-01] Invalid database host.")
        if not check_environment_value(ENV_DB_USERNAME):
            raise Exception(f"[Step:0-0-02] Invalid database username.")
        if not check_environment_value(ENV_DB_PASSWORD):
            raise Exception(f"[Step:0-0-03] Invalid database password.")
        if not check_environment_value(ENV_DB_DATABASE):
            raise Exception(f"[Step:0-0-04] Invalid database name.")
        if not check_environment_value(ENV_DB_SRID):
            raise Exception(f"[Step:0-0-05] Invalid SRID value.")
        if not check_environment_value(env_db_schema):
            raise Exception(f"[Step:0-0-06] Invalid database schema.")
        if not check_environment_value(env_db_tablename):
            raise Exception(f"[Step:0-0-07] Invalid database tablename.")
        ########################################################################################
        # Common local variables
        ########################################################################################
        if not os.path.exists("/tmp/data"):
            os.mkdir("/tmp/data")

        dir_data_inputs = "/tmp/data/inputs"
        dir_data_outputs = "/tmp/data/outputs"
        dir_logs = "/tmp/data/logs"

        #Existing Lambda results may exist, so remove them!
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

        ########################################################################################
        # Print variables
        ########################################################################################
        logger.debug(f"[Step:0-0-08] {ripple_file}")        #Required for Flows2Fim
        logger.debug(f"[Step:0-0-09] {input_flow_file}")    #Required for Flows2Fim
        logger.debug(f"[Step:0-0-10] {start_reaches_file}") #Required for Flows2Fim
        logger.debug(f"[Step:0-0-11] {library_folder}")     #Required for Flows2Fim

        logger.debug(f"[Step:0-0-12] {ENV_DB_HOST}")
        logger.debug(f"[Step:0-0-13] {ENV_DB_USERNAME}")
        logger.debug(f"[Step:0-0-14] {ENV_DB_PASSWORD}")
        logger.debug(f"[Step:0-0-15] {ENV_DB_DATABASE}")
        logger.debug(f"[Step:0-0-16] {env_db_schema}")
        logger.debug(f"[Step:0-0-17] {env_db_tablename}")
        logger.debug(f"[Step:0-0-18] {ENV_DB_SRID}")

        ########################################################################################
        ## Step 1: Set up logging
        ## Create and configure logger
        ########################################################################################
        if (console_debugging):
            print("[Step:1] Setting up logging")

        #Default log file name
        log_file = "LOG_Flows2Fim"
        current_time = datetime.now().strftime("%H:%M:%S")
        log_filename_local = dir_logs + "/"+ log_file + "_" + current_time + ".log"
        logger.add(log_filename_local)

        ########################################################################################
        ## Step 2: Get Ripple Input files
        ########################################################################################
        if (console_debugging):
            print("[Step:2] Download Ripple Files")        
            logger.debug(f"[Step:2-1-01] Download Ripple file {ripple_file}")
            logger.debug(f"[Step:2-1-02] Download Flows file {input_flow_file}")
            logger.debug(f"[Step:2-1-03] Download start reaches file {start_reaches_file}")

        download_data_result = get_all_data_inputs(ripple_file, input_flow_file, start_reaches_file, dir_data_inputs, console_debugging)
        if download_data_result == False:
             raise Exception(f"[Step:2] Failed to download Ripple data.")

        ########################################################################################
        ## Name of control file created locally
        ########################################################################################
        logger.debug(f"[Step:2-1-04] Checking control file settings")
        output_control_local_path = os.path.join(dir_data_outputs, "controls.csv")

        ########################################################################################
        ## Step 3: Execute Flows2Fim.exe Control file
        ########################################################################################
        if (console_debugging):
            print("[Step:3] Create Control file")
            logger.debug(f"[Step:3-0-00] {RIPPLE_LOCAL_PATH}")
            logger.debug(f"[Step:3-0-01] {FLOW_LOCAL_PATH}")
            logger.debug(f"[Step:3-0-02] {START_REACHES_LOCAL_PATH}")
            logger.debug(f"[Step:3-0-03] {output_control_local_path}")

        command_line = ["./flows2fim", "controls", "-db",RIPPLE_LOCAL_PATH,"-f",FLOW_LOCAL_PATH,"-scsv",START_REACHES_LOCAL_PATH,"-o",output_control_local_path]
        ans = subprocess.run(command_line, check=True, capture_output=True)
        
        #Beware, output such as WRN Large difference in target vs found flow reach_id
        # is not captured in CloudWatch Log Events.
        logger.debug(ans)

        if os.path.exists(output_control_local_path):
            file_size = os.path.getsize(output_control_local_path)
            logger.debug(f"[Step:3-0-1] Control file size {file_size}")

            #30 bytes is based on just a header returned. If no rows given unknown behavior expected.
            #For now, will cancel proceeding.
            if file_size < 30:
                logger.debug(f"[Step:3-0-2] Control file size created too small. '{file_size}' -> '{output_control_local_path}'")

                if upload_tracking:
                    track_changes( -1,-1,304)

                raise Exception(f"[Step:3] Flows2Fim.exe finished but created an EMPTY control file.")

        else:
            if upload_tracking:
                track_changes( -1,-1, 301)

            raise Exception(f"[Step:3] ERROR during the process of creating the Control file")

        ########################################################################################
        ## Step 4: Create FIM Vector results from Control File directly to database
        ########################################################################################
        if (console_debugging):
            print("[Step:4] Uploading vector to database")

        process_control_file_upload_to_database(library_folder,                  #Base S3 folder of HUC with FIM tifs
                                                output_control_local_path,       #Control file created from Step 3
                                                env_db_schema,                   #Schema of database destination
                                                env_db_tablename,                #Table Name of database destination
                                                console_debugging_for_every_tif, #For debugging purposes
                                                upload_tracking )                #Upload number of tifs processed to tracking table 

        ########################################################################################
        ## Wrap up
        ########################################################################################
        end_time = datetime.now()
        time_difference = end_time - START_TIME
        print(end_time.strftime("%Y-%m-%d %H:%M:%S")) 

        print("Time difference:", time_difference)
        print("[Ripple Main end]")

        if upload_tracking:
            tracemalloc.stop()

        result = {
            "statusCode": 200, 
            "body": json.dumps(f"Flows2Fim.exe container image finished in '{time_difference.total_seconds()}' seconds."),
            "headers": {
                "Content-Type": "application/json"
            }
        }
        return result

    ########################################################################################

    except Exception as e:
        traceback_str = traceback.format_exc()
        raise Exception(f"Stack trace errors. {event} --- {traceback_str}")

######################################################################################
if __name__ == "__main__":
    print("[Start] Ripple Lambda Function called from Main ", sys.argv)
    lambda_handler(sys.argv[1],sys.argv[2])
    print("[End] Ripple Lambda Function called from Main ", sys.argv)
