variable "environment" {
  description = "Hydrovis environment"
  type        = string
}

variable "account_id" {
  description = "Hydrovis environment"
  type        = string
}

variable "region" {
  description = "Hydrovis environment"
  type        = string
}

variable "viz_authoritative_bucket" {
  description = "S3 bucket where the viz authoritative data will live."
  type        = string
}

variable "fim_data_bucket" {
  description = "S3 bucket where the FIM data will live."
  type        = string
}

variable "fim_output_bucket" {
  description = "S3 bucket where the FIM outputs will live."
  type        = string
}

variable "deployment_bucket" {
  description = "S3 buckets where the lambda zip files will live."
  type        = string
}

variable "python_preprocessing_bucket" {
  description = "S3 bucket where the outputted max flows will live."
  type        = string
}

variable "rnr_data_bucket" {
  description = "S3 bucket where the rnr max flows will live."
  type        = string
}

variable "viz_cache_bucket" {
  description = "S3 bucket where the viz cache shapefiles will live."
  type        = string
}

variable "fim_version" {
  description = "Version of the FIM Package"
  type        = string
}

variable "hand_version" {
  description = "Version of HAND FIM"
  type        = string
}

variable "lambda_role" {
  description = "Role to use for the lambda functions."
  type        = string
}

variable "db_lambda_security_groups" {
  description = "Security group for db-pipeline lambdas."
  type        = list(any)
}

variable "db_lambda_subnets" {
  description = "Subnets to use for the db-pipeline lambdas."
  type        = list(any)
}

variable "nws_shared_account_nwm_sns" {
  type = string
}

variable "wrds_db_dump_sns" {
  type = string
}

variable "email_sns_topics" {
  description = "SnS topics"
  type        = map(any)
}

variable "viz_db_host" {
  description = "Hostname of the viz processing RDS instance."
  type        = string
}

variable "viz_db_name" {
  description = "DB Name of the viz processing RDS instance."
  type        = string
}

variable "egis_db_host" {
  description = "Hostname of the EGIS RDS instance."
  type        = string
}

variable "egis_db_name" {
  type = string
}

variable "viz_db_user_secret_string" {
  description = "The secret string of the viz_processing data base user to write/read data as."
  type        = string
}

variable "viz_db_suser_secret_string" {
  description = "The secret string of the viz_processing data base superuser to write/read data as."
  type        = string
}

variable "egis_db_user_secret_string" {
  description = "The secret string for the egis rds database."
  type        = string
}

variable "wrds_db_host" {
  description = "Hostname of the viz processing RDS instance."
  type        = string
}

variable "wrds_db_user_secret_string" {
  description = "The secret string of the viz_processing data base user to write/read data as."
  type        = string
}

variable "egis_portal_password" {
  description = "The password for the egis portal user to publish as."
  type        = string
}

variable "es_logging_layer" {
  type = string
}

variable "xarray_layer" {
  type = string
}

variable "pandas_layer" {
  type = string
}

variable "geopandas_layer" {
  type = string
}

variable "psycopg2_sqlalchemy_layer" {
  type = string
}

variable "arcgis_python_api_layer" {
  type = string
}

variable "requests_layer" {
  type = string
}

variable "yaml_layer" {
  type = string
}

variable "dask_layer" {
  type = string
}

variable "viz_lambda_shared_funcs_layer" {
  type = string
}

variable "viz_pipeline_step_function_arn" {
  type = string
}

variable "sync_wrds_db_step_function_arn" {
  type = string
}

variable "default_tags" {
  type = map(string)
}

variable "nwm_dataflow_version" {
  type = string
}

variable "five_minute_trigger" {
  type = object({
    name = string,
    arn = string
  })
}

variable "profile" {
  type = string
}

variable "creation_map" {
  type = map(string)
  default = {
    "all": true
  }
}

variable "execute_codebuild_function_name_override" {
  type = string
  default = null
}