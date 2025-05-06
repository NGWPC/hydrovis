# tools/read_schisim.py
import duckdb
import ibis
from ibis import _
import pandas as pd
import geopandas as gpd
import xarray as xr
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple
import os

ext_path = os.environ.get("DUCKDB_SPATIAL_EXTENSION_PATH")

# ----------------- Read 2dm file
def read_2dm(file_path: str) -> Tuple[List[List[float]], List[List[int]], pd.DataFrame, pd.DataFrame]:
    """
    Reads a 2DM file and extracts node and element data into structured lists and pandas DataFrames.

    Parameters:
    -----------
    file_path : str
        Path to the 2DM file.

    Returns:
    --------
    tuple:
        - node_data (List[List[float]]): A list of nodes where each node is represented as [node_id, x, y, z].
        - element_data (List[List[int]]): A list of elements where each element is represented as [element_id, node1, node2, node3].
        - nodes_df (pd.DataFrame): DataFrame containing nodes with columns ['node_id', 'x', 'y', 'z'].
        - elements_df (pd.DataFrame): DataFrame containing elements with columns ['element_id', 'node1', 'node2', 'node3'].

    Example:
    --------
    >>> node_data, element_data, nodes_df, elements_df = read_2dm("example.2dm")
    >>> print(nodes_df)
       node_id    x    y    z
    0        1  0.0  0.0  0.0
    1        2  1.0  0.0  0.0
    2        3  0.0  1.0  0.0
    >>> print(elements_df)
       element_id  node1  node2  node3
    0           1      1      2      3
    """
    node_data = []
    element_data = []

    with open(file_path, 'r') as file:
        for line in file:
            tokens = line.split()
            if not tokens:
                continue
            # Parse node entries (ND) and store node ID with x, y, z coordinates
            if tokens[0] == 'ND':
                node_id = int(tokens[1])
                x, y, z = map(float, tokens[2:5])
                node_data.append([node_id, x, y, z])
            # Parse triangular element entries (E3T) with 4 columns (ID + 3 node indices)
            elif tokens[0] == 'E3T':
                element_id = int(tokens[1])
                node_indices = list(map(int, tokens[2:5]))  # 3 node indices
                element_data.append([element_id] + node_indices)

    # Convert to pandas DataFrames
    nodes_df = pd.DataFrame(node_data, columns=['node_id', 'x', 'y', 'z'])
    elements_df = pd.DataFrame(element_data, columns=['element_id', 'node1', 'node2', 'node3'])

    return node_data, element_data, nodes_df, elements_df

# ----------------- Read gr3 file
def process_nodes(node_lines: List[List[str]]) -> pd.DataFrame:
    node_array = np.array(node_lines, dtype=float)
    return pd.DataFrame(node_array, columns=["node_id", "long", "lat", "wse"]).astype({"node_id": int})

def process_elements(element_lines: List[List[str]]) -> pd.DataFrame:
    element_array = np.array(element_lines, dtype=int)
    return pd.DataFrame(element_array, columns=["pg_id", "num_nodes", "node_id_1", "node_id_2", "node_id_3"]).astype({"pg_id": int})

def read_gr3(file_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, List[List[str]]]:
    """
    Reads a GR3 file and extracts node and element data into pandas DataFrames, 
    along with any extra lines that don't fit standard node or element formats.

    Parameters:
    -----------
    file_path : str
        Path to the GR3 file.

    Returns:
    --------
    tuple:
        - nodes_df (pd.DataFrame): DataFrame containing nodes with columns ['id', 'long', 'lat', 'swe'].
        - elements_df (pd.DataFrame): DataFrame containing elements with columns 
          ['pg_id', 'num_nodes', 'node_id_1', 'node_id_2', 'node_id_3'].
        - extra_lines (List[List[str]]): List of lines that do not conform to standard node or element formats.

    Example:
    --------
    >>> nodes_df, elements_df, extra_lines = read_gr3("example.gr3")
    >>> print(nodes_df)
       node_id  long  lat  wse
    0   1   0.0  0.0  1.0
    1   2   1.0  0.0  2.0
    2   3   0.0  1.0  3.0
    >>> print(elements_df)
       pg_id  num_nodes  node_id_1  node_id_2  node_id_3
    0      1          3          1          2          3
    """

    # Initialize storage for extra lines
    extra_lines = []

    # Prepare storage for node and element lines
    node_lines = []
    element_lines = []

    with open(file_path, 'r') as file:
        header = file.readline().strip()
        print("File Header:", header)

        # Classify lines in one pass
        for line in file:
            line = line.strip().split()
            if len(line) == 4:
                node_lines.append(line)
            elif len(line) == 5:
                element_lines.append(line)
            elif len(line) > 5:
                extra_lines.append(line)

    # Process nodes and elements concurrently
    with ThreadPoolExecutor() as executor:
        node_future = executor.submit(process_nodes, node_lines)
        element_future = executor.submit(process_elements, element_lines)

        # Retrieve results
        nodes_df = node_future.result()
        elements_df = element_future.result()

    print(f"Detected Nodes: {len(nodes_df)}, Elements: {len(elements_df)}, Extra Lines: {len(extra_lines)}")

    return nodes_df, elements_df, extra_lines

def read_netcdf(file_path :str) -> pd.DataFrame: 
    """
    Reads a .nc file using xarray and converts it to a pandas DataFrame.

    Args:
        file_path (str): The path to the .nc file.

    Returns:
        pandas.DataFrame: A DataFrame containing the data.
                           Returns None if there are issues reading the file.
    """
    try:
        ds = xr.open_dataset(file_path)
        # Print dataset info for exploration
        print(f"model TITLE: {ds.attrs.get('TITLE', 'No TITLE attribute found')}")
        print(f"Conventions: {ds.attrs.get('Conventions', 'No Conventions found')}") 
        print(f"code version: {ds.attrs.get('code_version', 'No code_version found')}") 
        print(f"NWM version number: {ds.attrs.get('NWM_version_number', 'No NWM_version_number found')}") 
        print(f"model output type: {ds.attrs.get('model_output_type', 'No model_output_type found')}") 
        print(f"model configuration: {ds.attrs.get('model_configuration', 'No model_configuration found')}") 
        print(f"model total valid times: {ds.attrs.get('model_total_valid_times', 'No model_total_valid_times found')}") 
        print(f"model initialization time: {ds.attrs.get('model_initialization_time', 'No model_initialization_time found')}") 
        print(f"model output valid time: {ds.attrs.get('model_output_valid_time', 'No model_output_valid_time found')}") 

        selected_variables = ['SCHISM_hgrid_node_x', 'SCHISM_hgrid_node_y', 'elevation'] 

        # Drop variables that aren't in the dataset, warning the user.
        valid_variables = [v for v in selected_variables if v in ds]
        invalid_variables = set(selected_variables) - set(valid_variables)
        if invalid_variables:
            print(f"Warning: The following variables were not found in the dataset: {invalid_variables}")

        if not valid_variables:
            print("No valid variables were selected, returning an empty DataFrame.")
            return pd.DataFrame()

        # Select the variables from the Dataset
        ds_selected = ds[valid_variables].load()
        df = ds_selected.to_dataframe().reset_index()

        # Create the node-index and rename appropriately
        df.rename(columns={'nSCHISM_hgrid_node': 'node_id', 'SCHISM_hgrid_node_x': 'long', 
                           'SCHISM_hgrid_node_y': 'lat', 'elevation': 'wse'}, inplace=True)
        
        if 'time' in df.columns:
            df.pop('time')

        df['node_id'] += 1

        return df

    except FileNotFoundError:
        print(f"Error: File not found at path: {file_path}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    
def crosswalk_nodes(database_path: str) -> None:
    """
    Matches nodes between nc and gr3 files using crosswalk tables and stores the result in 'nodes'.

    Args:
        database_path (str): Path to the DuckDB database file.

    Output:
        - A new or updated 'nodes' table 
    """
    data_conn = ibis.duckdb.connect(database_path)
    try:
        data_conn.raw_sql(f"LOAD '{ext_path}'")
    except Exception as e:
        raise RuntimeError(f"Failed to load DuckDB spatial extension from {ext_path}: {e}")
    data_conn.raw_sql(
        """
        CREATE OR REPLACE TABLE nodes AS
        SELECT 
            joined.node_id AS original_id,
            joined.node_id_gr3 AS node_id,
            joined.long,
            joined.lat,
            joined.wse
        FROM (
            SELECT
                nodes.*,
                node_cross_walk.*,
            FROM nodes
            LEFT JOIN node_cross_walk
            ON nodes.node_id = node_cross_walk.node_id_nc
        ) AS joined;
        """
    )
    data_conn.con.close()
    return
    
def index_triangles(triangles_path: str) -> None:
    """
    Adds a unique index to triangles by modifying the 'FID' column.

    Args:
        triangles_path (str): Path to the Parquet file containing triangle geometries.

    Output:
        - Updates the input Parquet file by renaming 'FID' to 'pg_id' and incrementing its values by 1.
    """
    triangle_shapes = gpd.read_parquet(triangles_path)
    triangle_shapes.rename(columns={'FID': 'pg_id'}, inplace=True)
    triangle_shapes['pg_id'] += 1
    triangle_shapes.to_parquet(triangles_path, index=False)
    return

def mask_elements(database_path: str) -> None:
    """
    Filters elements based on the 'masked_coverage_fraction' table and creates a new table.

    Args:
        database_path (str): Path to the DuckDB database file.

    Output:
        - A new or updated 'masked_elements' table containing only elements whose 'pg_id' 
          exists in the 'masked_coverage_fraction' table.
    """
    data_conn = ibis.duckdb.connect(database_path)
    try:
        data_conn.raw_sql(f"LOAD '{ext_path}'")
    except Exception as e:
        raise RuntimeError(f"Failed to load DuckDB spatial extension from {ext_path}: {e}")
    data_conn.raw_sql(
        f"""
        CREATE OR REPLACE TABLE masked_elements AS
        SELECT * FROM elements AS e
        WHERE e.pg_id IN (SELECT pg_id FROM masked_coverage_fraction);
        """
    )
    data_conn.con.close()
    return
