#######################
##     VARIABLES     ##
#######################
variable "viz_lambda_role" {
  type        = string
}

variable "environment" {
  type        = string
}

variable "ripple_fim_data_prep_arn" {
  type        = string
}

variable "ripple_fim_processing_arn" {
  type        = string
}

variable "ripple_fim_bucket" {
  type        = string
}

#######################
##     RESOURCES     ##
#######################

resource "aws_sfn_state_machine" "step_function" {
    name     = "hv-vpp-${var.environment}-ripple-fim-processing"
    role_arn = var.viz_lambda_role

    definition = sensitive(templatefile("${path.module}/ripple_fim_processing.json.tftpl", {
        ripple_fim_data_prep_arn  = var.ripple_fim_data_prep_arn
        ripple_fim_processing_arn = var.ripple_fim_processing_arn
        ripple_fim_bucket         = var.ripple_fim_bucket
    }))
}

#####################
##     OUTPUTS     ##
#####################

output "step_function" {
    value = aws_sfn_state_machine.step_function
}