#######################
##     VARIABLES     ##
#######################
variable "viz_lambda_role" {
  type        = string
}

variable "environment" {
  type        = string
}

variable "db_postprocess_sql_arn" {
  type        = string
}

variable "zonal_coastal_fim_processing_arn" {
  type = string
}

#######################
##     RESOURCES     ##
#######################

resource "aws_sfn_state_machine" "step_function" {
    name     = "hv-vpp-${var.environment}-process-schism-fim"
    role_arn = var.viz_lambda_role

    definition = sensitive(templatefile("${path.module}/schism_fim_processing.json.tftpl", {
        db_postprocess_sql_arn           = var.db_postprocess_sql_arn
        zonal_coastal_fim_processing_arn = var.zonal_coastal_fim_processing_arn
    }))
}

#####################
##     OUTPUTS     ##
#####################

output "step_function" {
    value = aws_sfn_state_machine.step_function
}