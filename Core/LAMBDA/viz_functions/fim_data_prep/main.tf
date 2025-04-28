terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      configuration_aliases = [ aws.no_tags ]
    }
  }
}

locals {
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
  function_name = "hv-vpp-${var.environment}-viz-fim-data-prep"
  description   = "Lambda function to setup a fim run by retriving max flows from the database, prepare an ingest database table, and creating a dictionary for huc-based worker lambdas to use."
  memory_size   = var.environment == "ti" ? 4096 : 2048 # Larger for apocalyptic testing
  timeout       = 900
  vpc_config {
    security_group_ids = var.db_lambda_security_groups
    subnet_ids         = var.db_lambda_subnets
  }
  environment {
    variables = {
      EGIS_DB_DATABASE        = var.egis_db_name
      EGIS_DB_HOST            = var.egis_db_host
      EGIS_DB_USERNAME        = jsondecode(var.egis_db_user_secret_string)["username"]
      EGIS_DB_PASSWORD        = jsondecode(var.egis_db_user_secret_string)["password"]
      PROCESSED_OUTPUT_BUCKET = var.fim_output_bucket
      PROCESSED_OUTPUT_PREFIX = "processing_outputs"
      FIM_VERSION             = var.fim_version
      VIZ_DB_DATABASE         = var.viz_db_name
      VIZ_DB_HOST             = var.viz_db_host
      VIZ_DB_USERNAME         = jsondecode(var.viz_db_user_secret_string)["username"]
      VIZ_DB_PASSWORD         = jsondecode(var.viz_db_user_secret_string)["password"]
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
    "Name" = "hv-vpp-${var.environment}-viz-fim-data-prep"
  }
}

output "lambda" {
    value = resource.aws_lambda_function.lambda
}