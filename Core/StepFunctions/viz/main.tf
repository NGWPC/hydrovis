locals {
  official_environments = ["ti", "uat", "prod"]
}
##################################################
##     Viz Process Schism FIM Step Function     ##
##################################################
module "schism-fim-processing" {
  count = var.schism_fim_processing_step_function_arn_override == null ? 1 : 0
  source = "./schism_fim_processing"

  viz_lambda_role = var.viz_lambda_role
  environment = var.environment
  schism_fim_job_definition_arn = var.schism_fim_job_definition_arn
  schism_fim_job_queue_arn = var.schism_fim_job_queue_arn
  schism_fim_datasets_bucket = var.schism_fim_datasets_bucket
  optimize_rasters_arn = var.optimize_rasters_arn
  db_postprocess_sql_arn = var.db_postprocess_sql_arn
}

########################################################
##     Zonal Coastal FIM Processing Step Function     ##
########################################################
module "zonal-coastal-fim-processing" {
  count = var.zonal_coastal_fim_processing_step_function_arn_override == null ? 1 : 0
  source = "./zonal_coastal_fim_processing"

  viz_lambda_role = var.viz_lambda_role
  environment = var.environment
  db_postprocess_sql_arn = var.db_postprocess_sql_arn
  zonal_coastal_fim_processing_arn = var.zonal_coastal_fim_processing_arn
}

###############################################
##     HAND FIM Processing Step Function     ##
###############################################
module "hand-fim-processing" {
  count = var.hand_fim_processing_step_function_arn_override == null ? 1 : 0
  source = "./hand_fim_processing"

  viz_lambda_role = var.viz_lambda_role
  environment = var.environment
  fim_data_prep_arn = var.fim_data_prep_arn
  hand_fim_processing_arn = var.hand_fim_processing_arn
}

###############################################
##    RIPPLE FIM Processing Step Function    ##
###############################################
module "ripple-fim-processing" {
  count = var.ripple_fim_processing_step_function_arn_override == null ? 1 : 0
  source = "./ripple_fim_processing"

  viz_lambda_role = var.viz_lambda_role
  environment = var.environment
  ripple_fim_data_prep_arn  = var.ripple_fim_data_prep_arn
  ripple_fim_processing_arn = var.ripple_fim_processing_arn
  ripple_fim_bucket         = var.ripple_fim_bucket
}

########################################
##     Viz Pipeline Step Function     ##
########################################
module "viz-processing-pipeline" {
  count = var.create_viz_processing_pipeline ? 1 : 0
  source = "./processing_pipeline"

  viz_lambda_role = var.viz_lambda_role
  environment = var.environment
  python_preprocessing_3GB_arn = var.python_preprocessing_3GB_arn
  python_preprocessing_10GB_arn = var.python_preprocessing_10GB_arn
  db_postprocess_sql_arn = var.db_postprocess_sql_arn
  db_ingest_arn = var.db_ingest_arn
  raster_processing_arn = var.raster_processing_arn
  optimize_rasters_arn = var.optimize_rasters_arn
  fim_data_prep_arn = var.fim_data_prep_arn
  update_egis_data_arn = var.update_egis_data_arn
  publish_service_arn = var.publish_service_arn
  schism_fim_processing_step_function_arn = var.schism_fim_processing_step_function_arn_override != null ? var.schism_fim_processing_step_function_arn_override : module.schism-fim-processing[0].step_function.arn
  zonal_coastal_fim_processing_step_function_arn = var.zonal_coastal_fim_processing_step_function_arn_override != null ? var.zonal_coastal_fim_processing_step_function_arn_override : module.zonal-coastal-fim-processing[0].step_function.arn
  hand_fim_processing_step_function_arn = var.hand_fim_processing_step_function_arn_override != null ? var.hand_fim_processing_step_function_arn_override : module.hand-fim-processing[0].step_function.arn
  ripple_fim_processing_step_function_arn = var.ripple_fim_processing_step_function_arn_override != null ? var.ripple_fim_processing_step_function_arn_override : module.ripple-fim-processing[0].step_function.arn
  viz_processing_pipeline_log_group = var.viz_processing_pipeline_log_group
}

####### Step Function Failure / Time Out SNS #######
resource "aws_cloudwatch_event_rule" "viz_pipeline_step_function_failure" {
  count     = contains(local.official_environments, var.environment) ? 1 : 0
  name        = "hv-vpp-${var.environment}-viz-pipeline-step-function-failure"
  description = "Alert when the viz step function times out or fails."

  event_pattern = <<EOF
  {
  "source": ["aws.states"],
  "detail-type": ["Step Functions Execution Status Change"],
  "detail": {
    "status": ["FAILED", "TIMED_OUT"],
    "stateMachineArn": ["${module.viz-processing-pipeline[0].step_function.arn}"]
    }
  }
  EOF
}

resource "aws_cloudwatch_event_target" "viz_pipeline_step_function_failure_sns" {
  count     = contains(local.official_environments, var.environment) ? 1 : 0
  rule        = aws_cloudwatch_event_rule.viz_pipeline_step_function_failure[0].name
  target_id   = "SendToSNS"
  arn         = var.email_sns_topics["viz_lambda_errors"].arn
  input_path  = "$.detail.name"
}

output "viz_pipeline_step_function" {
  value = var.create_viz_processing_pipeline ? module.viz-processing-pipeline[0].step_function : null
}