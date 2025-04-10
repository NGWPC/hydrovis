#import fsspec
import os
from viz_classes import database

import boto3
import os
import json
import tempfile
from urllib.parse import urlparse
import logging
import pandas as pd
import traceback

s3 = boto3.resource('s3') 
s3_client = boto3.client('s3')


class MissingS3FileException(Exception):
    """ my custom exception class """

#Helper function to check values from event inputs
def check_event_input(value):
    """
    Checks if the variable is a valid string.

    Parameters:
        variable: value to parse.

    Returns:
        bool: True if exists, False otherwise
    """
    result = True

    if not value.strip():
        return False
    if len(value) == 0:
        return False    
    if not value:
        return False  
    if value is None:
        return False    
 
    str_len = len(value)
    if str_len > 100:
        result = False

    return result

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

#Helper function to determine the given value is actually a string and not empty
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

#Helper function remove space generated during model table to csv file creation
def whitespace_remover(dataframe):
    # iterating over the columns
    for i in dataframe.columns:
        # checking datatype of each columns
        if dataframe[i].dtype == 'object':
            # applying strip function on column
            dataframe[i] = dataframe[i].map(str.strip)
        else:
            # if condn. is False then it will do nothing.
            pass

########################################################################################
# This function drops and re-creates the ripple tables that will store the FIM values and geometry.
# The main Ripple image will fill these tables later in the step function
# TODO error checking
def create_drop_ripple_table(arg_db_type, arg_db_schema, arg_db_tablename, arg_SRID):

    #TODO error checking
    input_db_type = arg_db_type
    db_schema = arg_db_schema
    db_tablename = arg_db_tablename
    viz_SRID = arg_SRID

    viz_db = database(db_type=input_db_type)
    sql_cmd = f"DROP TABLE IF EXISTS {db_schema}.{db_tablename};"
    resp = viz_db.execute_sql(sql_cmd) 

    sql_cmd = f"DROP SEQUENCE IF EXISTS {db_schema}.{db_tablename}_id_seq;"
    resp = viz_db.execute_sql(sql_cmd) 

    sql_cmd = f"CREATE SEQUENCE {db_schema}.{db_tablename}_id_seq START WITH 1;"
    resp = viz_db.execute_sql(sql_cmd) 

    sql_cmd = f"CREATE TABLE IF NOT EXISTS {db_schema}.{db_tablename} \
    (\
        oid integer NOT NULL DEFAULT nextval('{db_schema}.{db_tablename}_id_seq'::regclass),\
        feature_id character(25), \
        discharge_cfs character(25), \
        stage_ft character(25), \
        geom geometry(Polygon,{viz_SRID}),\
        CONSTRAINT {db_tablename}_pkey PRIMARY KEY (oid)\
    )"    

    resp = viz_db.execute_sql(sql_cmd) 

    #sql_cmd = f"TABLESPACE pg_default;" #TODO
    #resp = viz_db.execute_sql(sql_cmd) 

    sql_cmd = f"ALTER TABLE IF EXISTS {db_schema}.{db_tablename}\
        OWNER to viz_proc_admin_rw_user;"
    resp = viz_db.execute_sql(sql_cmd) 

    sql_cmd = f"CREATE INDEX IF NOT EXISTS sidx_{db_tablename}_geom\
        ON {db_schema}.{db_tablename} USING gist\
        (geom)\
        TABLESPACE pg_default;"  #TODO find out what tablespace to use
    
    resp = viz_db.execute_sql(sql_cmd) 

    #Clean up
    del viz_db

########################################################################################
# This function creates the flow files consumed by the Step function.
# This function WILL be the cause of memory issues. For earlier testing I had it at the lowest setting when
# using test tables. Once I started using larger tables memory usage increased and eventually reached the time limit (thrashing)
# TODO keep an eye on memory usage.
# TODO May need to do query chunking if memory usage is a problem
# TODO error checking
def create_flow_file(arg_db_type, arg_db_schema, arg_db_tablename, arg_flow_file_bucket, arg_flow_file_key):

    #TODO error checking
    result = True
    input_db_type = arg_db_type
    db_schema = arg_db_schema
    db_tablename = arg_db_tablename
    flow_file_bucket = arg_flow_file_bucket
    flow_file_key = arg_flow_file_key

    viz_db = database(db_type=input_db_type)
    
    #TODO make columns a variable if locations etc change
    query = f'''
    SELECT 
        max_forecast.feature_id, 
        max_forecast.discharge_cfs 
    FROM {db_schema}.{db_tablename} max_forecast
    JOIN derived.recurrence_flows_conus rf ON rf.feature_id = max_forecast.feature_id
    WHERE 
        max_forecast.discharge_cfs >= rf.high_water_threshold AND 
        rf.high_water_threshold > 0::double precision;
    '''

    result_df = viz_db.sql_to_dataframe(query) 
    
    print("Create CSV file from Database")
    tempdir = tempfile.mkdtemp()
    tmp_ouput_path = os.path.join(tempdir, f"temp_output.csv")

    #Remove any existing results, i.e. lambda cancelled etc
    if os.path.exists(str(tmp_ouput_path)):
        os.remove(tmp_ouput_path)

    result_df.to_csv(tmp_ouput_path, index=False)

    print("Uploading output CSV file to S3")
    output_flow_ripple_file = f"{db_schema}.{db_tablename}.csv" 
    output_bucket_flow_file = str(flow_file_key) + "/" + str(output_flow_ripple_file)

    try:
        print(f"--- Uploaded to s3://{flow_file_bucket}/{output_bucket_flow_file}")
        with open(tmp_ouput_path, "rb") as f:
            s3_client.upload_fileobj(f, flow_file_bucket, output_bucket_flow_file)
        
    except Exception as e:
        print(f"--- ERROR with uploading to s3://{flow_file_bucket}/{output_bucket_flow_file}")
        print(f"--- ERROR from table {db_schema}.{db_tablename}")
        result = False

    #Clean up, in case the same Lambda env gets reused
    if os.path.exists(str(tmp_ouput_path)):
        os.remove(tmp_ouput_path)

    del viz_db
    return result

########################################################################################
# This function creates the MAP csv file with the location of ripple model inputs and the flow table to use
# Comments:
#  1) We know folder contents are missing in the ripple folders. The image Lambda function just ignores these for now.
#  2) TODO This function needs access to a lookup table that matches feature-id/reach-id to a HUC 8 and ripple model
#     For development I'm skipping this step until after more larger tests
#     I would expect that parts of this lookup already exists, will be a matter of connecting logic
#  3) TODO For now the csv file will use a single flow table input. 
#     --Could mix and match the flow tables, depending on testing with geoparquet files (TODO) later. Using a partition strategy.
#     --The goal is to use this file as a "logic" style file meaning the main Ripple lambda engine does not care where the data is, or the inputs.
#  4) TODO I'm not a fan of repeating the same flow input file in the MAP csv file.
#     --If we stick with this development method of creating vectors on the fly, then the flow input is redundant and can be replaced with state variable
#     --If we continue with geoparquet in the future, I forsee mixing and matching flow inputs with geoparquet partitioning  
#  5) Using a table to query the main model components
#     --Will provide flexibility of mixing and matching buckets and paths.
#  6) TODO THIS LIST IS NOT UNIQUE ATM based on FIM huc conditions.
#     --i.e. its a static result all the time ATM
#  7) TODO check no spaces in model S3 bucket paths

def create_ripple_model_input_file(
        arg_input_s3_model_csv_url, # S3 Url to csv file for ripple_model_list (Table name stored with model)
        arg_flow_file_s3_fullpath,  #i.e. full path of flow file in S3 bucket
        arg_output_file_bucket,     #i.e. bucket location where to place this file
        arg_output_file_key,        #i.e. bucket folder only (Based on env variable)
        arg_output_file_name,       #i.e. Name of model file name created by this function
        arg_output_schema,          #Schema for destination output table
        arg_output_table_name):   

    #TODO error checking
    result = True

    input_s3_model_csv_url = arg_input_s3_model_csv_url
    flow_s3_full_filename_path = arg_flow_file_s3_fullpath
    output_file_bucket = arg_output_file_bucket
    output_file_key = arg_output_file_key
    output_model_file = arg_output_file_name

    destination_schema_table_name = arg_output_schema + "." + arg_output_table_name
    
    #TODO Look at other HV code and follow existing patterns
    #TODO error checking
    #Issues with ffspec, then sf3, then aiobotocore
    #result_df = pd.read_csv(input_s3_model_csv_url)
    print(input_s3_model_csv_url)
    model_local_path = '/tmp/model_list.csv'
    model_bucket, model_key, model_fname = parse_s3_url_GET_bucket_key_filename(input_s3_model_csv_url)
    s3.Bucket(model_bucket).download_file(model_key, model_local_path)
    result_df = pd.read_csv(model_local_path)

 
    print("Create CSV file from Database")
    tempdir = tempfile.mkdtemp()
    tmp_ouput_path = os.path.join(tempdir, f"temp_model.csv")

    #Remove any existing results, i.e. lambda cancelled etc
    if os.path.exists(str(tmp_ouput_path)):
        os.remove(tmp_ouput_path)

    # Remove all spaces, including spaces within the string
    # TODO what happens when model names have spaces in them?
    whitespace_remover(result_df)
    #result_df = result_df.apply(lambda x: x.astype(str).str.replace(" ", ""))

    result_df['destination_schema_table_name'] = destination_schema_table_name
    result_df['maxFlowTable'] = flow_s3_full_filename_path
    result_df.to_csv(tmp_ouput_path, index=False)

    print("Uploading output CSV file to S3")
    output_bucket_model_file = str(output_file_key) + "/" + str(output_model_file)

    try:
        print(f"--- Uploading to s3://{output_file_bucket}/{output_bucket_model_file}")
        with open(tmp_ouput_path, "rb") as f:
            s3_client.upload_fileobj(f, output_file_bucket, output_bucket_model_file)
        
    except Exception as e:
        print(f"--- ERROR with uploading s3://{output_file_bucket}/{output_bucket_model_file}")
        print(f"--- ERROR from model S3 file {input_s3_model_csv_url}")
        result = False

    #Clean up, in case the same Lambda env gets reused
    if os.path.exists(str(tmp_ouput_path)):
        os.remove(tmp_ouput_path)

    return result    
    
def lambda_handler(event, context):

    try:
        arg_input_flow_schema_table = ""
        arg_output_flow_schema_table = ""
        arg_output_map_file = ""

        try:
            arg_input_flow_schema_table = event['flows_table']
        except KeyError:
            return {
                'statusCode': 9000,
                'message': f"[Step:0-0-1] Flows Table argument missing. {event}"
            }
        
        try:
            arg_output_flow_schema_table = event['target_table']
        except KeyError:
            return {
                'statusCode': 9001,
                'message': f"[Step:0-0-2] Target Table argument missing. {event}"
            }
        
        try:
            arg_output_map_file = event['map_file']
        except KeyError:
            return {
                'statusCode': 9002,
                'message': f"[Step:0-0-3] Map file argument missing. {event}"
            }
                    
        test1 = check_event_input(arg_input_flow_schema_table)
        if test1 == False:
            return {
                'statusCode': 9003,
                'message': f"[Step:0-0-4] Flows Table argument missing. {event}"
            }            

        test2 = check_event_input(arg_output_flow_schema_table)
        if test2 == False:
            return {
                'statusCode': 9004,
                'message': f"[Step:0-0-5] Flows Table argument missing. {event}"
            } 
        
        test3 = check_event_input(arg_output_map_file)
        if test3 == False:
            return {
                'statusCode': 9005,
                'message': f"[Step:0-0-6] Flows Table argument missing. {event}"
            } 

        return main(arg_input_flow_schema_table, arg_output_flow_schema_table, arg_output_map_file)
    
    except Exception as e:
        tmp_str = traceback.print_exc() 
        return {
            'statusCode': 9010,
            'body': json.dumps(f"[lambda_handler] TraceBack -> {tmp_str}.")
        }          
    
def main(input_flows_table, output_schema_table, output_map_file):

    console_debugging = True

    ########################################################################################
    ## [1-0-0] Check environmental variables configured by Lambda Function
    ########################################################################################

    #TODO Decide if batch at once, or one variable at a time from HV Step functions
    #cache.max_flows_[ana|srf|mrf_nbm_[3|5|10]day|mrf_gfs_[3|5|10]day]

    input_table_split = input_flows_table.split('.')
    split_len = len(input_table_split)
    if split_len != 2:
        return {
            'statusCode': 600,
            'body': json.dumps(f"[Step:0-1-1] Invalid flows table => {input_table_split}")
        }
            
    env_in_flow_db_schema = input_table_split[0]
    env_in_flow_db_table = input_table_split[1]

    if (console_debugging): 
        print(env_in_flow_db_schema)
        print(env_in_flow_db_table)

    output_table_split = output_schema_table.split('.')
    split_len = len(output_table_split)
    if split_len != 2:
        return {
            'statusCode': 601,
            'body': json.dumps(f"[Step:0-1-1] Invalid output table  => {output_table_split}")
        }

    output_db_schema = output_table_split[0]
    output_db_table = output_table_split[1]

    if console_debugging == True: 
        print(output_db_schema)
        print(output_db_table)    

    ########################################################################################

    # This list focuses on table output creation
    env_out_db_host = os.getenv('VIZ_DB_HOST')                  #rds-viz.hydrovis.internal:5432
    env_out_db_username = os.getenv('VIZ_DB_USERNAME')          #viz_proc_admin_rw_user
    env_out_db_password = os.getenv('VIZ_DB_PASSWORD')          #
    env_out_db_database = os.getenv('VIZ_DB_DATABASE')          #vizprocessing
    env_out_viz_SRID = os.getenv('VIZ_OUT_SRID')                #3857
    env_out_S3_bucket = os.getenv('VIZ_OUT_S3_BUCKET_LOCATION') #s3://hv-vpp-dev-ripple/dev_temp/LorneLeonard/LAMBDA_WORKSPACE/

    if not check_environment_value(env_out_db_host):
        return {
            'statusCode': 610,
            'body': json.dumps(f"[Step:0-1-1] Invalid output database host.")
        }
    if not check_environment_value(env_out_db_username):
        return {
            'statusCode': 611,
            'body': json.dumps(f"[Step:0-1-2] Invalid output database username.")
        }
    if not check_environment_value(env_out_db_password):
        return {
            'statusCode': 612,
            'body': json.dumps(f"[Step:0-1-3] Invalid output database password.")
        }
    if not check_environment_value(env_out_db_database):
        return {
            'statusCode': 613,
            'body': json.dumps(f"[Step:0-1-4] Invalid output database name.")
        }                                
    if not check_environment_value(env_out_viz_SRID):
        return {
            'statusCode': 616,
            'body': json.dumps(f"[Step:0-1-7] Invalid output SRID value.")
        }    

    # Bad S3 bucket will raise error here
    # REMEMBER this S3 url does not have a fullname, needs to be added below
    # This S3 path is considered the base folder. It is assumed the subfolders are already in placed.
    output_flow_and_model_file_bucket, output_flow_and_model_file_key = parse_s3_url_GET_bucket_key(env_out_S3_bucket)

    if console_debugging == True:
        print("Bucket:", output_flow_and_model_file_bucket)
        print("Key:", output_flow_and_model_file_key)

    ########################################################################################
    ## [2-0-0] Delete existing vector table results in database and recreate tables
    ########################################################################################

    output_db_type = "viz" #TODO
    output_SRID = env_out_viz_SRID
    create_drop_ripple_table(output_db_type,   #TODO
                             output_db_schema, #Provided as function argument output_schema_table
                             output_db_table,  #Provided as function argument output_schema_table
                             output_SRID)

    ########################################################################################
    ## [3-0-0] Create Ripple flows.csv input file
    ########################################################################################

    error_found_flow = False
    input_flow_db_type = "viz" #TODO

    #TI bucket structure
    output_flow_and_model_file_key_folder = output_flow_and_model_file_key + "/flow_files"
    result = create_flow_file(input_flow_db_type,                       #i.e. viz
                                env_in_flow_db_schema,                   #i.e. cache
                                env_in_flow_db_table,                   #i.e. max_flows_srf
                                output_flow_and_model_file_bucket,      #i.e. bucket location where to place this file
                                output_flow_and_model_file_key_folder)  #i.e. key here is the folder location. Does not include file name.

    if result == False:
        logging.exception(f"Error creating flow file for {input_flow_db_type} {env_in_flow_db_schema} {env_in_flow_db_table} {output_flow_and_model_file_bucket} {output_flow_and_model_file_key_folder}")
        error_found_flow = True

    if error_found_flow == True:
        return {
            'statusCode': 620,
            'body': json.dumps(f'Error found while creating flow input files.')
        }
    
    ########################################################################################
    ## [4-0-0] Create csv file for Map Step Function
    ########################################################################################

    error_found_model = False

    #TI bucket structure
    input_s3_model_csv_url = str(env_out_S3_bucket) + "/model_lookup_file/ripple_model_list.csv" 
    #Error checking happens in create_ripple_model_input_file function

    flow_full_s3_path = f"s3://{output_flow_and_model_file_bucket}/{output_flow_and_model_file_key_folder}/{env_in_flow_db_schema}.{env_in_flow_db_table}.csv"
    if console_debugging == True:
        print(flow_full_s3_path)

    #TI bucket structure
    output_ripple_folder = output_flow_and_model_file_key + "/model_files"

    result = create_ripple_model_input_file(
            input_s3_model_csv_url,            #i.e. S3 Url to csv file with ripple_model_list (Table name stored with model)
            flow_full_s3_path,                 #i.e. full path of flow file in S3 bucket
            output_flow_and_model_file_bucket, #i.e. bucket location where to place this file
            output_ripple_folder,              #i.e. bucket folder
            output_map_file,                   #i.e. name of file to create
            output_db_schema,                  #Schema output location used by Ripple image
            output_db_table)                  #Table output location used by Ripple image
  
    if result == False:
        logging.exception(f"Error creating model file for {env_in_flow_db_schema} {output_db_table} {output_flow_and_model_file_bucket} {output_flow_and_model_file_key}")
        error_found_model = True

    if error_found_model == True:
        return {
            'statusCode': 630,
            'body': json.dumps(f'Error found while creating model input files.')
        }
    
    return {
        'statusCode': 200,
        'body': json.dumps(f'Created tables and flow file for Ripples')
    }
