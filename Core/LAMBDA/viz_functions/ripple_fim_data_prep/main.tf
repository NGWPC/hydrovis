terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      configuration_aliases = [ aws.no_tags ]
    }
  }
}

data "archive_file" "deploy_zip" {
  type = "zip"

  source_file = "${path.module}/viz_ripple_fim_data_prep/lambda_function.py"

  output_path = "${path.module}/temp/viz_ripple_fim_data_prep_${var.environment}_${var.region}.zip"
}

resource "aws_s3_object" "deploy_zip_upload" {
  provider = aws.no_tags  
  bucket      = var.deployment_bucket
  key         = "terraform_artifacts/${path.module}/viz_ripple_fim_data_prep.zip"
  source      = data.archive_file.deploy_zip.output_path
  source_hash = filemd5(data.archive_file.deploy_zip.output_path)
}

resource "aws_lambda_function" "lambda" {
  function_name = "hv-vpp-${var.environment}-viz-ripple-fim-data-prep"
  description   = "Lambda function to create Ripple flows file and tables."
  memory_size   = 1024
  timeout       = 900
  vpc_config {
    security_group_ids = var.db_lambda_security_groups
    subnet_ids         = var.db_lambda_subnets
  }
  environment {
    variables = {
      VIZ_DB_DATABASE = var.viz_db_name
      VIZ_DB_HOST     = var.viz_db_host
      VIZ_DB_USERNAME = jsondecode(var.viz_db_user_secret_string)["username"]
      VIZ_DB_PASSWORD = jsondecode(var.viz_db_user_secret_string)["password"]
      VIZ_OUT_SRID    = "3857"
      VIZ_OUT_BUCKET = "${var.ripple_bucket}"
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
    "Name" = "hv-vpp-${var.environment}-viz-ripple-fim-data-prep"
  }
}

output "lambda" {
    value = resource.aws_lambda_function.lambda
}