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
  short_name = "execute-codebuild"
  full_name = "hv-vpp-${var.environment}-${local.short_name}"
}

data "archive_file" "deploy_zip" {
  type = "zip"
  output_path = "${path.module}/temp/${var.environment}_${var.region}_deploy.zip"
  source_dir = "${path.module}/deploy/code"
}

resource "aws_s3_object" "deploy_zip_upload" {
  provider = aws.no_tags  
  bucket      = var.deployment_bucket
  key         = "terraform_artifacts/${local.viz_service_path}/${var.environment}/deploy.zip"
  source      = data.archive_file.deploy_zip.output_path
  source_hash = filemd5(data.archive_file.deploy_zip.output_path)
}

resource "aws_lambda_function" "lambda" {
  function_name = local.full_name
  description   = "Lambda function to test the wrds_location3_ondeck db before it is swapped for the live version"
  timeout       = 300
  memory_size   = 512
  vpc_config {
    security_group_ids = var.db_lambda_security_groups
    subnet_ids         = var.db_lambda_subnets
  }
  s3_bucket        = aws_s3_object.deploy_zip_upload.bucket
  s3_key           = aws_s3_object.deploy_zip_upload.key
  source_code_hash = filebase64sha256(data.archive_file.deploy_zip.output_path)
  runtime          = "python3.9"
  handler          = "lambda_function.lambda_handler"
  role             = var.viz_role
  tags = {
    "Name" = local.full_name
  }
}