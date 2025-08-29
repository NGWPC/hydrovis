terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      configuration_aliases = [ aws.sns, aws.no_tags]
    }
  }
}

locals {
  raster_output_prefix     = "processing_outputs"
  ingest_flow_threshold    = 0.001
  viz_service_path = "${split("Core/", abspath(path.module))[1]}"
}

data "archive_file" "deploy_zip" {
  type = "zip"
  source_dir = "${path.module}/deploy/code"
  output_path = "${path.module}/temp/${var.environment}_${var.region}_deploy.zip"
}

resource "aws_s3_object" "deploy_zip_upload" {
  provider = aws.no_tags  
  bucket      = var.deployment_bucket
  key         = "terraform_artifacts/${local.viz_service_path}/${var.environment}/deploy.zip"
  source      = data.archive_file.deploy_zip.output_path
  source_hash = filemd5(data.archive_file.deploy_zip.output_path)
}

resource "aws_lambda_function" "lambda" {
  function_name = "hv-vpp-${var.environment}-viz-initialize-pipeline"
  description   = "Lambda function to receive automatic input from sns or lambda invocation, parse the event, construct a pipeline dictionary, and invoke the viz pipeline state machine with it."
  memory_size   = 128
  timeout       = 300
  vpc_config {
    security_group_ids = var.db_lambda_security_groups
    subnet_ids         = var.db_lambda_subnets
  }
  environment {
    variables = {
      SF_ARN__VIZ_PIPELINE         = var.viz_pipeline_step_function_arn
      SF_ARN__SYNC_WRDS_DB         = var.sync_wrds_db_step_function_arn
      SNS_TOPIC__WRDS_DB_DUMP      = var.wrds_db_dump_sns
      DATA_BUCKET_UPLOAD           = var.fim_output_bucket
      PYTHON_PREPROCESSING_BUCKET  = var.python_preprocessing_bucket
      RNR_DATA_BUCKET              = var.rnr_data_bucket
      RASTER_OUTPUT_BUCKET         = var.fim_output_bucket
      RASTER_OUTPUT_PREFIX         = local.raster_output_prefix
      INGEST_FLOW_THRESHOLD        = local.ingest_flow_threshold
      VIZ_DB_DATABASE              = var.viz_db_name
      VIZ_DB_HOST                  = var.viz_db_host
      VIZ_DB_USERNAME              = jsondecode(var.viz_db_user_secret_string)["username"]
      VIZ_DB_PASSWORD              = jsondecode(var.viz_db_user_secret_string)["password"]
      NWM_DATAFLOW_VERSION         = var.nwm_dataflow_version
    }
  }
  s3_bucket        = aws_s3_object.deploy_zip_upload.bucket
  s3_key           = aws_s3_object.deploy_zip_upload.key
  source_code_hash = filebase64sha256(data.archive_file.deploy_zip.output_path)
  runtime          = "python3.9"
  handler          = "lambda_function.lambda_handler"
  role             = var.lambda_role
  layers = var.layers
  tags = {
    "Name" = "hv-vpp-${var.environment}-viz-initialize-pipeline"
  }
}

output "lambda" {
    value = resource.aws_lambda_function.lambda
}