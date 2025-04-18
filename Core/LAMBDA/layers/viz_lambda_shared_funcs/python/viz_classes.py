import datetime
import os
import json
import re
import urllib.parse
import inspect
import pathlib
try:
    import fsspec
except:
    print("fsspec not found, will fall back to boto3")

class RequiredTableNotUpdated(Exception):
    """ This is a custom exception to report back to the AWS Step Function that a required table does not exist or has not yet been updated with the current reference time. """

###################################################################################################################################################
###################################################################################################################################################
class database: #TODO: Should we be creating a connection/engine upon initialization, or within each method like we are now?
    def __init__(self, db_type):
        self.type = db_type.upper()
        self._engine = None
        self._connection = None
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self._connection:
            self._connection.close()
    
    @property
    def engine(self):
        if not self._engine:
            self._engine = self.get_db_engine()
        return self._engine

    @property
    def connection(self):
        if not self._connection:
            self._connection = self.get_db_connection()
        return self._connection
    
    ###################################
    def get_db_credentials(self):
        db_host = os.environ[f'{self.type}_DB_HOST']
        db_name = os.environ[f'{self.type}_DB_DATABASE']
        db_user = os.environ[f'{self.type}_DB_USERNAME']
        db_password = os.getenv(f'{self.type}_DB_PASSWORD')
        return db_host, db_name, db_user, db_password

    ###################################
    def get_db_engine(self):
        from sqlalchemy import create_engine
        db_host, db_name, db_user, db_password = self.get_db_credentials()
        db_engine = create_engine(f'postgresql://{db_user}:{db_password}@{db_host}/{db_name}')
        print(f"***> Established db engine to: {db_host} from {inspect.stack()[1].function}()")
        return db_engine

    ###################################
    def get_db_connection(self, asynchronous=False):
        import psycopg2
        db_host, db_name, db_user, db_password = self.get_db_credentials()
        port = 5439 if self.type == "REDSHIFT" else 5432
        connection = psycopg2.connect(f"host={db_host} dbname={db_name} user={db_user} password={db_password} port={port}", async_=asynchronous)
        print(f"***> Established db connection to: {db_host} from {inspect.stack()[1].function}()")
        return connection

    ###################################
    def get_db_values(self, table, columns):
        import pandas as pd
        db_engine = self.engine
        if not type(columns) == list:
            raise Exception("columns argument must be a list of column names")
        columns = ",".join(columns)
        print(f"---> Retrieving values for {columns}")
        df = pd.read_sql(f'SELECT {columns} FROM {table}', db_engine)
        db_engine.dispose()
        return df
    
    ###################################
    def load_df_into_db(self, table_name, df, drop_first=True):
        import pandas as pd
        schema = table_name.split(".")[0]
        table = table_name.split(".")[-1]
        db_engine = self.engine
        if drop_first:
            print(f"---> Dropping {table_name} if it exists")
            db_engine.execute(f'DROP TABLE IF EXISTS {table_name};')  # Drop the stage table if it exists
            print("---> Getting sql to create table")
            create_table_statement = pd.io.sql.get_schema(df, table_name)
            replace_values = {'"geom" TEXT': '"geom" GEOMETRY', "REAL": "DOUBLE PRECISION"}  # Correct data types
            for a, b in replace_values.items():
                create_table_statement = create_table_statement.replace(a, b)
            create_table_statement = create_table_statement.replace(f'"{table_name}"', table_name)
            print(f"---> Creating {table_name}")
            db_engine.execute(create_table_statement)  # Create the new empty stage table
        print(f"---> Adding data to {table_name}")
        df.to_sql(con=db_engine, schema=schema, name=table, index=False, if_exists='append')
        db_engine.dispose()

    ###################################
    def execute_sql(self, sql):
        if sql.endswith('.sql') and os.path.exists(sql):
            sql = pathlib.Path(sql).read_text()
        with self.connection:
            try:
                with self.connection.cursor() as cur:
                    print(f"---> Running provided SQL:\n{sql}")
                    cur.execute(sql)
            except Exception as e:
                raise e
                
    ###################################                
    def sql_to_dataframe(self, sql, return_geodataframe=False):
        if sql.endswith(".sql"):
            sql = pathlib.Path(sql).read_text()
            
        db_engine = self.engine
        if not return_geodataframe:
            import pandas as pd
            df = pd.read_sql(sql, db_engine)
        else:
            import geopandas as gdp
            df = gdp.GeoDataFrame.from_postgis(sql, db_engine)
        
        db_engine.dispose()
        return df

    ###################################
    def get_est_row_count_in_table(self, table):
        print(f"Getting estimated total rows in {table}.")
        with self.connection:
            try:
                with self.connection.cursor() as cur:
                    sql = f"""
                    SELECT (CASE WHEN c.reltuples < 0 THEN NULL -- never vacuumed
                                WHEN c.relpages = 0 THEN float8 '0' -- empty table
                                ELSE c.reltuples / c.relpages END
                        * (pg_catalog.pg_relation_size(c.oid) / pg_catalog.current_setting('block_size')::int))::bigint
                    FROM   pg_catalog.pg_class c
                    WHERE  c.oid = '{table}'::regclass; -- schema-qualified table here
                    """
                    cur.execute(sql)
                    rows = cur.fetchone()[0]
            except Exception as e:
                raise e

        return rows
    
    ###################################
    def move_data_to_another_db(self, dest_db_type, origin_table, dest_table, stage=True, add_oid=True, add_geom_index=True, chunk_size=200000):
        import pandas as pd
        origin_engine = self.engine
        dest_db = self.__class__(dest_db_type)
        dest_engine = dest_db.get_db_engine()
        if stage:
            dest_final_table = dest_table
            dest_final_table_name = dest_final_table.split(".")[1]
            dest_table = f"{dest_table}_stage"
        total_rows = self.get_est_row_count_in_table(origin_table) + 50000 #adding 50000 for buffer since this is estimated
        print(f"---> Reading {origin_table} from the {self.type} db")
        dest_engine.execute(f'DROP TABLE IF EXISTS {dest_table};')  # Drop the destination table if it exists
        
        # Chunk the copy into multiple parts if necessary
        for x in range(0, total_rows, chunk_size):
            print(f"Copying Chunk: LIMIT {chunk_size} OFFSET {x}")
            df = pd.read_sql(f'SELECT * FROM {origin_table} LIMIT {chunk_size} OFFSET {x};', origin_engine)  # Read from the newly created table
            drop_first = True if x == 0 else False
            dest_db.load_df_into_db(dest_table, df, drop_first=drop_first)
        
        if add_oid:
            print(f"---> Adding an OID to the {dest_table}")
            dest_engine.execute(f'ALTER TABLE {dest_table} ADD COLUMN OID SERIAL PRIMARY KEY;')
        if add_geom_index:
            print(f"---> Adding an spatial index to the {dest_table}")
            dest_engine.execute(f'CREATE INDEX ON {dest_table} USING GIST (geom);')  # Add a spatial index
        if stage:
            print(f"---> Renaming {dest_table} to {dest_final_table}")
            dest_engine.execute(f'DROP TABLE IF EXISTS {dest_final_table};')  # Drop the published table if it exists
            dest_engine.execute(f'ALTER TABLE {dest_table} RENAME TO {dest_final_table_name};')  # Rename the staged table
        origin_engine.dispose()
        dest_engine.dispose()
    
    ###################################
    def cache_data(self, table, reference_time, retention_days=30):
        retention_cutoff = reference_time - datetime.timedelta(retention_days)
        ref_prefix = f"ref_{reference_time.strftime('%Y%m%d_%H%M_')}"
        retention_prefix = f"ref_{retention_cutoff.strftime('%Y%m%d_%H%M_')}"
        new_archive_table = f"archive.{ref_prefix}{table}"
        cutoff_archive_table = f"archive.{retention_prefix}{table}"
        db_engine = self.engine
        db_engine.execute(f'DROP TABLE IF EXISTS {new_archive_table};')
        db_engine.execute(f'DROP TABLE IF EXISTS {cutoff_archive_table};')
        db_engine.execute(f'SELECT * INTO {new_archive_table} FROM publish.{table};')
        db_engine.dispose()
        print(f"---> Wrote cache data into {new_archive_table} and dropped corresponding table from {retention_days} days ago, if it existed.")
    
    ###########################################
    def check_required_tables_updated(self, sql_path_or_str, sql_replace={}, reference_time=None, stop_on_first_issue=True, raise_if_false=False):
        """ Determines if tables required by provided SQL path or string are updated as expected

        Args:
            sql_path_or_str (str): Path to SQL file or raw SQL string
            sql_replace (dict): Dictionary containing find/replace values for SQL, if applicable
            reference_time (str): The reference_time that should be compared against for tables that contain a
                reference_time column. If the table does not contain that column, it is
                considered to be up to date
            stop_on_first_issue (bool): If True, the first issue encountered will cause the script to terminate
                either returning false or raising an exception if raise_if_false is also True. If False, every
                error will be explored before returning (only useful if raise_if_false is True since the error
                message will thus contain all relevant failures, rather than just the first.)
            raise_if_false (bool): If True, a custom RequiredTableNotUpdated exception will be raised
                if either a table does not exist, or if the reference_time column
                exists its current value does not match the provided reference_time. The specific
                details of the failure will be included in the exception message, which will only
                be the first failure encountered unless stop_on_first_issue is False.
        
        Raises:
            RequiredTableNotUpdated if raise_if_false is True
        
        Returns:
            Bool. True if no issues encountered, False otherwise.
        """
        issues_encountered = []
        # Determine if arg is file or raw SQL string
        if os.path.exists(sql_path_or_str):
            sql = pathlib.Path(sql_path_or_str).read_text()
        else:
            sql = sql_path_or_str
        
        for word, replacement in sql_replace.items():
            sql = re.sub(word, replacement, sql, flags=re.IGNORECASE).replace('utc', 'UTC')
        
        output_tables = set(re.findall(r'(?<=INTO\s)\w+\.\w+', sql, flags=re.IGNORECASE)) 
        input_tables = set(re.findall(r'(?<=FROM\s|JOIN\s)\w+\.\w+', sql, flags=re.IGNORECASE))
        check_tables = input_tables - output_tables

        if not check_tables:
            return True
        
        # This next 3 lines were added specifically to abort checking cache.max_flows_ana when creating 
        # cache.max_flows_ana_past_hour since cache.max_flow_ana will always be an hour behind at the 
        # time of creating the past_hour table. Rather than hard-code it exactly, I've left it more generalized 
        # in case other similar cases come up. But this could ideally be removed once We figure out a 
        # new method for storing the past hour of max_flows_ana.
        if any('past' in t for t in output_tables):
            return True

        # Required tables exist and should be checked
        with self.connection as connection:
            cur = connection.cursor()
            for table in check_tables:
                if issues_encountered and stop_on_first_issue:
                    break
                schemaname, tablename = table.lower().split('.')
                sql = f'''
                    SELECT EXISTS (
                        SELECT FROM 
                            information_schema.tables
                        WHERE 
                            table_schema = '{schemaname}' AND 
                            table_name  = '{tablename}'
                    );
                '''
                cur.execute(sql)
                table_exists = cur.fetchone()[0]

                if not table_exists:
                    issues_encountered.append(f'Table {table} does not exist.')
                    continue
                
                # Table exists.

                if not reference_time or any(x in table for x in ['past', 'ahps']):
                    continue
                
                # Reference time provided.
                
                # Check if reference_time column exists and if its entry matches
                sql = f'''
                    SELECT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_schema='{schemaname}' AND table_name='{tablename}' AND column_name='reference_time'
                    );
                '''
                cur.execute(sql)
                reftime_col_exists = cur.fetchone()[0]
                if not reftime_col_exists:
                    continue
                
                # Column 'reference_time' exists
                
                # Check if it matches
                sql = f"SELECT reference_time FROM {table} LIMIT 1"
                cur.execute(sql)
                reftime_result = cur.fetchone()
                if not reftime_result: # table is empty
                    issues_encountered.append(f'Table {table} is empty.')
                    continue
            
                data_reftime = reftime_result[0].replace(" UTC", "")
                if data_reftime != reference_time: # table reference time matches current reference time
                    issues_encountered.append(f'Table {table} has unexpected reftime. Expected {reference_time} but found {data_reftime}.')
                    continue

        if issues_encountered:
            if raise_if_false:
                raise RequiredTableNotUpdated(' '.join(issues_encountered))
            return False
        return True

###################################################################################################################################################
###################################################################################################################################################
class s3_file:
    try:
        fs = fsspec.filesystem('s3')
    except:
        pass

    def __init__(self, bucket, key):
        self.bucket = bucket
        self.key = key
        self.uri = 's3://' + bucket + '/' + key

    ###################################
    @classmethod
    def from_lambda_event(cls, event):
        print("Parsing lambda event to get S3 key and bucket.")
        if "Records" in event:
            message = json.loads(event["Records"][0]['Sns']['Message'])
            data_bucket = message["Records"][0]['s3']['bucket']['name']
            data_key = urllib.parse.unquote_plus(message["Records"][0]['s3']['object']['key'], encoding='utf-8')
        else:
            data_bucket = event['data_bucket']
            data_key = event['data_key']
        return cls(data_bucket, data_key)

    ###################################
    @classmethod
    def from_eventbridge(cls, event):
        configuration = event['resources'][0].split("/")[-1]
        eventbridge_time = datetime.datetime.strptime(event['time'], '%Y-%m-%dT%H:%M:%SZ')

        coastal = False
        if "coastal" in configuration:
            coastal = True
            
        forcing = False
        if "forcing" in configuration:
            forcing = True

        if "hawaii" in configuration:
            domain = "hawaii"
        elif "puertorico" in configuration:
            domain = "puertorico"
        elif "alaska" in configuration:
            domain = "alaska"
        else:
            domain = "conus"

        if "analysis_assim" in configuration:
            if "14day" in configuration:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0, hour=0)
            elif coastal and domain in ["conus", "puertorico"]:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=1)
            else:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0)
        elif "short_range" in configuration:
            if domain in ["hawaii", "puertorico"]:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=3)
            elif domain == "alaska":
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=1)
            elif coastal:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=2)
            else:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=1)
        elif "medium_range" in configuration:
            if forcing:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=5)
            elif domain == "alaska":
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=6)
            elif coastal:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=13)
            else:
                reference_time = eventbridge_time.replace(microsecond=0, second=0, minute=0) - datetime.timedelta(hours=7)

        bucket = os.environ.get("DATA_BUCKET_UPLOAD") if os.environ.get("DATA_BUCKET_UPLOAD") else "nomads"

        reference_time = reference_time - datetime.timedelta(hours=1)
        
        return configuration, reference_time, bucket

    ###################################
    @classmethod
    def get_most_recent_from_configuration(cls, configuration_name, bucket):
        # Set the S3 prefix based on the confiuration
        def get_s3_prefix(configuration_name, date):
            if configuration_name == 'replace_route':
                prefix = f"replace_route/{date}/wrf_hydro/"
            elif configuration_name == 'ahps':
                prefix = f"max_stage/ahps/{date}/"
            else:
                nwm_dataflow_version = os.environ.get("NWM_DATAFLOW_VERSION") if os.environ.get("NWM_DATAFLOW_VERSION") else "prod"
                if configuration_name == 'medium_range_ensemble':
                    configuration_name == 'medium_range_mem6'
                prefix = f"common/data/model/com/nwm/{nwm_dataflow_version}/nwm.{date}/{configuration_name}/"
                
            return prefix
            
        # Get all S3 files that match the bucket / prefix
        def list_s3_files(bucket, prefix):
            try:
                files = cls.fs.ls(f"{bucket}/{prefix}", detail=True)
                return [f for f in files if f['type'] == 'file']
            except:
                import boto3
                
                s3 = boto3.client('s3')
                files = []
                paginator = s3.get_paginator('list_objects_v2')
                for result in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for key in result['Contents']:
                        # Skip folders
                        if not key['Key'].endswith('/'):
                            files.append(key['Key'])
                if len(files) == 0:
                    raise Exception("No Files Found.")
                return files
        # Start with looking at files today, but try yesterday if that doesn't work (in case this runs close to midnight)
        today = datetime.datetime.today().strftime('%Y%m%d')
        yesterday = (datetime.datetime.today() - datetime.timedelta(1)).strftime('%Y%m%d')
        try:
            files = list_s3_files(bucket, get_s3_prefix(configuration_name, today))
        except Exception as e:
            print(f"Failed to get files for today ({e}). Trying again with yesterday's files")
            files = list_s3_files(bucket, get_s3_prefix(configuration_name, yesterday))
        # It seems this list is always sorted by default, but adding some sorting logic here may be necessary
        file = cls(bucket=bucket, key=files[-1:].pop())
        return file

    ###################################
    def check_existence(self):
        try:
            return self.fs.exists(f"{self.bucket}/{self.key}")
        except:
            import boto3
            from botocore.exceptions import ClientError

            s3_resource = boto3.resource('s3')
            try:
                s3_resource.Object(self.bucket, self.key).load()
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == "404":
                    return False
                else:
                    raise

###################################################################################################################################################
###################################################################################################################################################
def get_elasticsearch_logger():
    import logging
    logger = logging.getLogger('elasticsearch')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        # Prevent logging from propagating to the root logger
        logger.propagate = 0
        console = logging.StreamHandler()
        logger.addHandler(console)
        formatter = logging.Formatter('[ELASTICSEARCH %(levelname)s]:  %(asctime)s - %(message)s')
        console.setFormatter(formatter)
    return logger