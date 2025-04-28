#######################
##     VARIABLES     ##
#######################
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

variable "optimize_rasters_arn" {
  type        = string
}

variable "update_egis_data_arn" {
  type        = string
}

variable "fim_data_prep_arn" {
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

variable "viz_processing_pipeline_log_group" {
  type        = string
}

variable "schism_fim_processing_step_function_arn" {
  type = string
}

variable "hand_fim_processing_step_function_arn" {
  type = string
}


#######################
##     RESOURCES     ##
#######################

resource "aws_sfn_state_machine" "step_function" {
    name     = "hv-vpp-${var.environment}-viz-pipeline"
    role_arn = var.viz_lambda_role

    definition = sensitive(templatefile("${path.module}/viz_processing_pipeline.json.tftpl", {
      python_preprocessing_3GB_arn = var.python_preprocessing_3GB_arn
      python_preprocessing_10GB_arn = var.python_preprocessing_10GB_arn
      db_postprocess_sql_arn = var.db_postprocess_sql_arn
      db_ingest_arn = var.db_ingest_arn
      raster_processing_arn = var.raster_processing_arn
      optimize_rasters_arn = var.optimize_rasters_arn
      fim_data_prep_arn = var.fim_data_prep_arn
      update_egis_data_arn = var.update_egis_data_arn
      publish_service_arn = var.publish_service_arn
      schism_fim_processing_step_function_arn = var.schism_fim_processing_step_function_arn
      hand_fim_processing_step_function_arn = var.hand_fim_processing_step_function_arn
      viz_processing_pipeline_log_group = var.viz_processing_pipeline_log_group
    }))
}

#####################
##     OUTPUTS     ##
#####################

output "step_function" {
    value = aws_sfn_state_machine.step_function
}