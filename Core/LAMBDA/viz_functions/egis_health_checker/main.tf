terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      configuration_aliases = [aws.no_tags]
    }
  }
}

locals {
  s3_artifact_path = "${split("Core/", abspath(path.module))[1]}"
}

data "archive_file" "deploy_zip" {
  type = "zip"
  source_dir = "${path.module}/deploy/code"
  output_path = "${path.module}/temp/${var.environment}_${var.region}_deploy.zip"
}

resource "aws_s3_object" "deploy_zip_upload" {
  provider = aws.no_tags  
  bucket      = var.deployment_bucket
  key         = "terraform_artifacts/${local.s3_artifact_path}/${var.environment}/deploy.zip"
  source      = data.archive_file.deploy_zip.output_path
  source_hash = filemd5(data.archive_file.deploy_zip.output_path)
}

resource "aws_lambda_function" "lambda" {
  function_name = "hv-vpp-${var.environment}-egis-health-checker"
  description   = "Lambda function to ping WRDS API and format outputs for processing."
  memory_size   = 512
  timeout       = 300

  vpc_config {
    security_group_ids = var.db_lambda_security_groups
    subnet_ids         = var.db_lambda_subnets
  }

  environment {
    variables = {
      GIS_HOST = var.environment == "prod" ? "maps.water.noaa.gov" : var.environment == "uat" ? "maps-staging.water.noaa.gov" : var.environment == "ti" ? "maps-testing.water.noaa.gov" : "hydrovis-dev.nwc.nws.noaa.gov"
    }
  }
  s3_bucket        = aws_s3_object.deploy_zip_upload.bucket
  s3_key           = aws_s3_object.deploy_zip_upload.key
  source_code_hash = filebase64sha256(data.archive_file.deploy_zip.output_path)
  runtime          = "python3.9"
  handler          = "lambda_function.lambda_handler"
  role             = var.lambda_role
  layers = [
    var.requests_layer
  ]
  tags = {
    "Name" = "hv-vpp-${var.environment}-egis-health-checker"
  }
}

output "lambda" {
    value = resource.aws_lambda_function.lambda
}