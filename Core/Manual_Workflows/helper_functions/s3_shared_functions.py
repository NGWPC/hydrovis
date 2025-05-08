
# This script will eventually cover all types of communication with S3
# from get lists, uploading, downloading, moving, etc.
import fnmatch
import io
import os
import re
import sys

import boto3
import pandas as pd

sys.path.append(os.path.abspath('..'))


# =======================================================
# *****************************
# CAUTION:  TODO: Aug 2024: This needs to be re-thought. It can easily overpower the notebook server depending on teh size of the notebooks
# *****************************
def load_S3_csv_to_df(bucket_name, s3_file_path, aws_access_id, aws_access_key, aws_session_token, is_verbose=False):
    '''
    Returns:
        - A dataframe with the single csv data loaded
    '''

    if s3_file_path is None or s3_file_path == '' or len(s3_file_path) < 5:
        raise Exception("s3_file_path is invalid - not set, empty or too short")

    if s3_file_path.endswith(".csv") is False:
        raise Exception(f"File name is not valid (not a csv): {s3_file}")
    
    # Manage the direction of the slashes just cases
    s3_file_path = s3_file_path.replace("\\", "/")

    if s3_file_path.startswith("/"):  # remove it
        s3_file_path = s3_file.lstrip("/")

    full_file_url = f"s3://{bucket_name}/{s3_file_path}"
    if is_verbose:
        print(f".. Downloading: {full_file_url}")

    s3_session = boto3.Session(
      aws_access_key_id=aws_access_id,
      aws_secret_access_key=aws_access_key,
      aws_session_token=aws_session_token
    )
    s3_client = s3_session.client('s3')

    # Read CSV from S3
    df = pd.DataFrame()
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_file_path)
        csv_content = response['Body'].read()
        df = pd.read_csv(io.BytesIO(csv_content))
        # print(df)
    except Exception as e:
        print(f"**** Error reading CSV from S3: {e}")

    if is_verbose:
        print(".. Downloading complete")

    return df

# ======================================================
def get_s3_subfolder_file_names(bucket_name, s3_src_folder_prefix, search_key,
                                is_in_branches = False, is_verbose = False):

    '''
    Overview: Gets a list of file (not folders in a s3 folder (well.. prefix)

    Note: This gets files at both the HUC level and branch level. 

    Usage Examples:
    ie) "some bucket", "fim/hand_4_6_1_4/hand_dataset, True, "

    Args:
        - s3_src_folder_prefix: string with or without slashes.
            ie) fim/hand_bridge_test/hand_datasets
        - search_key (string): Can only use full or partial file names,
          but you can use wildcard of *. As always * is 0 to many.  Case sensitive.
          It searchs recursively.
        - if is_in_branches = true, it will look for only files that have a subfolder
          with the name "branches" in its path. Why have it? some files have the same
          file name at both the huc level and the branch level. Note, this tool
          can be uses against non-hand folders, jsut ensure this flag says false

    returns:
        a list of file names and path (keys), without including the bucket and src_folder_path

    Note: Something to watch for.
        At the HUC level, there is a file named hydrotable.csv (the 't' is lower case)
        But at the branch level, they are called hydroTables_{branch}.csv  (upper case 't')

    # Examples:
    # search_key = "hydrotable*"  (none... only work if no chars in front of hydrotable)
    # search_key = "*hydrotable*"
    # search_key = "hydrotable*.cav"

    '''

    s3_client = boto3.client("s3")

    default_kwargs = {"Bucket": bucket_name, "Prefix": s3_src_folder_prefix}

    next_token = ""

    file_list = []

    print(f"Getting file list from s3://{bucket_name}/{s3_src_folder_prefix}")
    print(f"search key is {search_key}")
    print("")
    while next_token is not None:
        updated_kwargs = default_kwargs.copy()
        if next_token != "":
            updated_kwargs["ContinuationToken"] = next_token

        # will limit to 1000 objects - hence tokens, even for list_objects_v2
        response = s3_client.list_objects_v2(**updated_kwargs)
        if response.get("KeyCount") == 0:
            # some recs may have been added in earlier pages
            next_token = response.get("NextContinuationToken")
            continue

        contents = response.get("Contents")
        if contents is None:
            raise Exception("s3 contents not did not load correctly")

        for result in contents:
            key = result.get("Key")
            if key[-1] == "/":  # if it was a folder (ending in a slash, we skip it)
                continue

            if is_verbose:
                print(f"Key is {key}")

            if search_key == "":
                file_list.append(key)
                continue

            # break the key down to its' last file name
            key_file_name = key.split('/')[-1]
            # print(f"key file name is ...{key_file_name}...")
            if fnmatch.fnmatch(key_file_name, search_key) is True:
                if is_in_branches:
                    if "branches" in key:
                        file_list.append(key)
                else:
                    file_list.append(key)

        next_token = response.get("NextContinuationToken")
    # end of while

    print(f"Found {len(file_list)} file names from s3://{bucket_name}/{s3_src_folder_prefix}")
    return file_list

