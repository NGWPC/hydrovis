import fsspec
import os
import rioxarray as rxr
from rasterio.crs import CRS
from datetime import datetime
from viz_lambda_shared_funcs import check_if_file_exists, generate_file_list


def lambda_handler(event, context):
    product_name = event['product']['product']

    file_pattern = event['product']['raster_input_files']['file_format']
    file_step = event['product']['raster_input_files']['file_step']
    file_window = event['product']['raster_input_files']['file_window']
    product_file = event['product']['raster_input_files']['product_file']
    input_bucket = event['product']['raster_input_files']['bucket']

    output_bucket = event['product']['raster_outputs']['output_bucket']
    output_workspace = event['product']['raster_outputs']['output_raster_workspaces'][0][product_name]
    reference_time = event['reference_time']
    reference_date = datetime.strptime(reference_time, "%Y-%m-%d %H:%M:%S")

    file_step = None if file_step == "None" else file_step
    file_window = None if file_window == "None" else file_window
    
    input_files = generate_file_list(file_pattern, file_step, file_window, reference_date)

    try:
        func = getattr(__import__(f"products.{product_file}", fromlist=["main"]), "main")
    except AttributeError:
        raise Exception(f'product_file not found for {product_file}')

    uploaded_rasters = func(product_name, input_bucket, input_files, reference_time, output_bucket, output_workspace)
        
    event['output_rasters'] = {
        "output_rasters": uploaded_rasters,
        "output_bucket": output_bucket
    }

    return event

def open_raster(bucket, file, variable):
    download_path = check_if_file_exists(bucket, file, download=True)
    print(f"--> Downloaded {file} to {download_path}")
    
    print(f"Opening {variable} in raster for {file}")
    ds = rxr.open_rasterio(download_path, variable=variable)
    
    # for some files like NBM alaska, the line above opens the attribute itself
    try:
        data = ds[variable]
    except:
        data = ds

    proj4 = ds.proj4
    crs = CRS.from_proj4(proj4)
    os.remove(download_path)
    return data, crs

def create_raster(data, crs, raster_name):
    print(f"Creating raster for {raster_name}")
    data.rio.write_crs(crs, inplace=True)
    data.rio.write_nodata(0, inplace=True)
    
    if "grid_mapping" in data.attrs:
        data.attrs.pop("grid_mapping")
        
    if "_FillValue" in data.attrs:
        data.attrs.pop("_FillValue")

    local_raster = f'/tmp/{raster_name}.tif'

    print(f"Saving raster to {local_raster}")
    data.rio.to_raster(local_raster)
    
    return local_raster

def upload_raster(local_raster, output_bucket, output_workspace):
    raster_name = os.path.basename(local_raster)
    s3_raster_key = f"s3://{output_bucket}/{output_workspace}/tif/{raster_name}"
    
    print(f"--> Uploading raster to {s3_raster_key}")
    s3 = fsspec.filesystem('s3')
    s3.put_file(local_raster, s3_raster_key)
    os.remove(local_raster)
    return s3_raster_key

def sum_rasters(bucket, input_files, variable):
    print(f"Adding {variable} variable of {len(input_files)} raster(s)...")
    sum_initiated = False
    for input_file in input_files:
        print(f"Adding {input_file}...")
        data, crs = open_raster(bucket, input_file, variable)
        time_index = 0
        if len(data.time) > 1:
            time_index = -1
            for i, t in enumerate(data.time):
                if str(float(data.sel(time=t)[0][0])) != 'nan':
                    time_index = i
                    break
            if (time_index < 0):
                raise Exception(f"No valid time steps were found in file: {input_file}")
        
        if not sum_initiated:
            data_sum = data.sel(time=data.time[time_index])
            sum_initiated = True
        else:
            data_sum += data.sel(time=data.time[time_index])
    print("Done adding rasters!")
    return data_sum, crs
