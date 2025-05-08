variable "viz_lambda_role" {
  type        = string
}

variable "environment" {
  type        = string
}

variable "python_preprocessing_3GB_arn" {
  type        = string
}

variable "python_preprocessing_10GB_arn" {
  type        = string
}

variable "schism_fim_job_definition_arn" {
  type        = string
}

variable "schism_fim_job_queue_arn" {
  type        = string
}

variable "schism_fim_datasets_bucket" {
  type        = string
}

variable "ripple_fim_bucket" {
  type        = string
}

variable "optimize_rasters_arn" {
  type        = string
}

variable "update_egis_data_arn" {
  type        = string
}

variable "fim_data_prep_arn" {
  type        = string
}

variable "ripple_fim_data_prep_arn" {
  type        = string
}

variable "ripple_fim_processing_arn" {
  type        = string
}

variable "hand_fim_processing_arn" {
  type        = string
}

variable "db_postprocess_sql_arn" {
  type        = string
}

variable "db_ingest_arn" {
  type        = string
}

variable "raster_processing_arn" {
  type        = string
}

variable "publish_service_arn" {
  type        = string
}

variable "email_sns_topics" {
  description = "SnS topics"
  type        = map(any)
}

variable "viz_processing_pipeline_log_group" {
  type        = string
}

variable "schism_fim_processing_step_function_arn_override" {
    type = string
    default = null
}

variable "hand_fim_processing_step_function_arn_override" {
    type = string
    default = null
}

variable "ripple_fim_processing_step_function_arn_override" {
  type = string
  default = null
}