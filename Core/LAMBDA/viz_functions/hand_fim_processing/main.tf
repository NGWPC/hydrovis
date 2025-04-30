terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      configuration_aliases = [ aws.no_tags ]
    }
  }
}

locals {
  viz_service_name = "viz-hand-fim-processing"
  viz_lambda_name = "hv-vpp-${var.environment}-${local.viz_service_name}"
  viz_service_path = "${split("Core/", abspath(path.module))[1]}"
}


data "archive_file" "deploy_zip" {
  type = "zip"
  output_path = "${path.module}/temp/${var.environment}_${var.region}_deploy.zip"

  dynamic "source" {
    for_each = fileset("${path.module}/deploy", "**")
    content {
      content  = sensitive(file("${path.module}/deploy/${source.key}"))
      filename = source.key
    }
  }

  source {
    content  = sensitive(file("${path.module}/../../layers/viz_lambda_shared_funcs/python/viz_classes.py"))
    filename = "code/viz_classes.py"
  }

  source {
    content = templatefile("${path.module}/serverless.yml.tmpl", {
      SERVICE_NAME = replace(local.viz_lambda_name, "_", "-")
      LAMBDA_TAGS = jsonencode(merge(var.default_tags, { Name = local.viz_lambda_name }))
      DEPLOYMENT_BUCKET = var.deployment_bucket
      AWS_DEFAULT_REGION = var.region
      LAMBDA_NAME = local.viz_lambda_name
      AWS_ACCOUNT_ID = var.account_id
      IMAGE_REPO_NAME = aws_ecr_repository.image.name
      IMAGE_TAG = var.ecr_repository_image_tag
      LAMBDA_ROLE_ARN = var.lambda_role
      FIM_VERSION        = var.fim_version
      HAND_BUCKET        = var.fim_data_bucket
      HAND_VERSION       = var.hand_version
      VIZ_DB_DATABASE = var.viz_db_name
      VIZ_DB_HOST = var.viz_db_host
      VIZ_DB_USERNAME = jsondecode(var.viz_db_user_secret_string)["username"]
      VIZ_DB_PASSWORD = jsondecode(var.viz_db_user_secret_string)["password"]
      EGIS_DB_DATABASE   = var.egis_db_name
      EGIS_DB_HOST       = var.egis_db_host
      EGIS_DB_USERNAME   = jsondecode(var.egis_db_user_secret_string)["username"]
      EGIS_DB_PASSWORD   = jsondecode(var.egis_db_user_secret_string)["password"]
      AUTH_DATA_BUCKET = var.viz_authoritative_bucket
      SECURITY_GROUP_1   = var.security_groups[0]
      SUBNET_1           = var.subnets[0]
      SUBNET_2           = var.subnets[1]
    })
    filename = "serverless.yml"
  }
}

resource "aws_s3_object" "deploy_zip_upload" {
  provider = aws.no_tags  
  bucket      = var.deployment_bucket
  key         = "terraform_artifacts/${local.viz_service_path}/${var.environment}/deploy.zip"
  source      = data.archive_file.deploy_zip.output_path
  source_hash = data.archive_file.deploy_zip.output_md5
}

resource "aws_ecr_repository" "image" {
  name                 = local.viz_lambda_name
  image_tag_mutability = "MUTABLE"

  force_delete = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_codebuild_project" "codebuild" {
  name          = local.viz_lambda_name
  description   = "Codebuild project that builds the lambda container based on a zip file with lambda code and dockerfile. Also deploys a lambda function using the ECR image"
  build_timeout = "60"
  service_role  = var.lambda_role

  artifacts {
    type = "NO_ARTIFACTS"
  }

  environment {
    compute_type                = "BUILD_GENERAL1_SMALL"
    image                       = "aws/codebuild/amazonlinux-aarch64-standard:3.0"
    type                        = "ARM_CONTAINER"
    image_pull_credentials_type = "CODEBUILD"
    privileged_mode             = true

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.region
    }

    environment_variable {
      name  = "AWS_ACCOUNT_ID"
      value = var.account_id
    }

    environment_variable {
      name  = "IMAGE_REPO_NAME"
      value = aws_ecr_repository.image.name
    }

    environment_variable {
      name  = "IMAGE_TAG"
      value = var.ecr_repository_image_tag
    }
  }

  source {
    type     = "S3"
    location = "${aws_s3_object.deploy_zip_upload.bucket}/${aws_s3_object.deploy_zip_upload.key}"
  }
}

resource "aws_lambda_invocation" "execute_codebuild" {
  function_name = var.execute_codebuild_function_name

  triggers = {
    function_update = data.archive_file.deploy_zip.output_md5
  }

  input = jsonencode({
    project_name = resource.aws_codebuild_project.codebuild.name
  })
}

data "aws_lambda_function" "lambda" {
  function_name = local.viz_lambda_name

  depends_on = [
    resource.aws_lambda_invocation.execute_codebuild
  ]
}