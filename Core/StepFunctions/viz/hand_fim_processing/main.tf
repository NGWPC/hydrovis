#######################
##     VARIABLES     ##
#######################
variable "viz_lambda_role" {
  type        = string
}

variable "environment" {
  type        = string
}

variable "fim_data_prep_arn" {
  type        = string
}

variable "hand_fim_processing_arn" {
  type        = string
}

#######################
##     RESOURCES     ##
#######################

resource "aws_sfn_state_machine" "step_function" {
    name     = "hv-vpp-${var.environment}-hand-fim-processing"
    role_arn = var.viz_lambda_role

    definition = sensitive(templatefile("${path.module}/hand_fim_processing.json.tftpl", {
        fim_data_prep_arn  = var.fim_data_prep_arn
        hand_fim_processing_arn = var.hand_fim_processing_arn
    }))
}

#####################
##     OUTPUTS     ##
#####################

output "step_function" {
    value = aws_sfn_state_machine.step_function
}