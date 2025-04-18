#######################
##     VARIABLES     ##
#######################
variable "viz_lambda_role" {
  type        = string
}

variable "environment" {
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

variable "optimize_rasters_arn" {
  type        = string
}

variable "db_postprocess_sql_arn" {
  type        = string
}

#######################
##     RESOURCES     ##
#######################

resource "aws_sfn_state_machine" "step_function" {
    name     = "hv-vpp-${var.environment}-process-schism-fim"
    role_arn = var.viz_lambda_role

    definition = templatefile("${path.module}/schism_fim_processing.json.tftpl", {
        db_postprocess_sql_arn          = var.db_postprocess_sql_arn
        schism_fim_job_definition_arn   = var.schism_fim_job_definition_arn
        schism_fim_job_queue_arn        = var.schism_fim_job_queue_arn
        optimize_rasters_arn            = var.optimize_rasters_arn
        schism_fim_datasets_bucket      = var.schism_fim_datasets_bucket
    })
}

#####################
##     OUTPUTS     ##
#####################

output "step_function" {
    value = aws_sfn_state_machine.step_function
}