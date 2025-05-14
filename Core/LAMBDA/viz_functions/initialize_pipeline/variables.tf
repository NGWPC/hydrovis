variable "environment" {
  description = "Hydrovis environment"
  type        = string
}

variable "region" {
  description = "Hydrovis environment"
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

variable "wrds_db_dump_sns" {
  type = string
}

variable "viz_db_host" {
  description = "Hostname of the viz processing RDS instance."
  type        = string
}

variable "viz_db_name" {
  description = "DB Name of the viz processing RDS instance."
  type        = string
}

variable "viz_db_user_secret_string" {
  description = "The secret string of the viz_processing data base user to write/read data as."
  type        = string
}

variable "layers" {
    type = list(string)
}

variable "viz_pipeline_step_function_arn" {
  type = string
}

variable "sync_wrds_db_step_function_arn" {
  type = string
}

variable "nwm_dataflow_version" {
  type = string
}

