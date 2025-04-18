terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      configuration_aliases = [ aws.sns, aws.no_tags]
    }
  }
}

locals {
  viz_service_path = "${split("Core/", abspath(path.module))[1]}"
}

data "archive_file" "deploy_zip" {
  type = "zip"
  output_path = "${path.module}/temp/${var.environment}_${var.region}_deploy.zip"

  source {
    content  = file("${path.module}/deploy/code/lambda_function.py")
    filename = "lambda_function.py"
  }

  dynamic "source" {
    for_each = fileset("${path.module}../", "**/*.sql")
    content {
      content  = file("${path.module}/${source.key}")
      filename = "sql_files/${basename(source.key)}"
    }
  }
}

resource "aws_s3_object" "deploy_zip_upload" {
  provider = aws.no_tags  
  bucket      = var.deployment_bucket
  key         = "terraform_artifacts/${local.viz_service_path}/${var.environment}/deploy.zip"
  source      = data.archive_file.deploy_zip.output_path
  source_hash = filemd5(data.archive_file.deploy_zip.output_path)
}

resource "aws_lambda_function" "lambda" {
  function_name = "hv-vpp-${var.environment}-viz-test-wrds-db"
  description   = "Lambda function to test the wrds_location3_ondeck db before it is swapped for the live version"
  timeout       = 900
  memory_size   = 5000
  vpc_config {
    security_group_ids = var.db_lambda_security_groups
    subnet_ids         = var.db_lambda_subnets
  }
  environment {
    variables = {
      WRDS_DB_HOST      = var.wrds_db_host
      WRDS_DB_USERNAME  = jsondecode(var.wrds_db_user_secret_string)["username"]
      WRDS_DB_PASSWORD  = jsondecode(var.wrds_db_user_secret_string)["password"]
      VIZ_DB_DATABASE   = var.viz_db_name
      VIZ_DB_HOST       = var.viz_db_host
      VIZ_DB_USERNAME   = jsondecode(var.viz_db_suser_secret_string)["username"]
      VIZ_DB_PASSWORD   = jsondecode(var.viz_db_suser_secret_string)["password"]
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
    "Name" = "hv-vpp-${var.environment}-viz-test-wrds-db"
  }
}