variable "environment" {
  type = string
}

variable "region" {
  type = string
}

variable "artifact_bucket_name" {
  type = string
}

variable "builder_role_instance_profile_name" {
  type = string
}

variable "builder_sg_id" {
  type = string
}

variable "builder_subnet_id" {
  type = string
}

variable "ami_sharing_account_ids" {
  type = list(string)
}

variable "egis_service_account_password" {
  type = string
}

data "aws_key_pair" "ec2" {
  key_name = "hv-${var.environment}-ec2-key-pair-${var.region}"
}

data "aws_ssm_parameter" "arcgisenterprise_version" {
  name = "/esri-builds/ec2-imagebuilder/arcgis_version"
}

data "aws_default_tags" "default" {
}

locals {
  # generate dashed-version name
  arcgisVersionName = replace(data.aws_ssm_parameter.arcgisenterprise_version.value, ".", "-")
  # role to use for image builder
  aws_role = "svc-EC2-ImageSTIG-builder"
  # prefix all builds with this
  ami_name_prefix = "hydrovis-egis-windows-stig"
  # pipeline internal versioning
  image_version = "1.6.2"
  # where pipeline logs will get written
  imageBuilderLogBucket = "hydrovis-11-3-deployment"
  # where software/chef configs get downloaded
  deploymentS3Source = "s3://hydrovis-11-3-deployment/software/v11-3"
  # chef configs to be used
  arcgisenterpriseConfig = "install-arcgis-enterprise-base.json"
  arcgisServerConfig     = "install-arcgis-server.json"
  # working folder on the build machine
  # deployment scripts depend on this folder
  # don't change without updating those
  WorkingFolder = "c:/software"
  # ssm parameter base path that we will store the AMI IDs for reference
  # by other applications
  aws_ssm_egis_amiid_store = "/esri-builds"
  # default number of days for cloudwatch logs
  lambda_cloud_watch_log_group_retention_in_days = 14
  # tags that we want to apply to this whole deployment and the images
  shared_tags = {
    "Contact" : "robert.van@noaa.gov",
    "Service" : "Esri Professional Services",
    "CodeDeployContact" : "drix.tabligan@noaa.gov",
    "CodeDeployService" : "Gama1 HydroVIS Support Team"
    # anything you want for tags
  }
  # regions to distribute the generated images to
  destination_aws_regions = ["us-east-1", "us-east-2"]
  ti_account_id           = "526904826677"
}

resource "aws_imagebuilder_infrastructure_configuration" "arcgis_build_infrastructure" {
  name                          = "arcgis_build_infrastructure"
  description                   = "Infrastructure to build ArcGIS images"
  instance_profile_name         = aws_iam_instance_profile.EC2-ImageSTIG-builder.name
  instance_types                = ["m5.xlarge"]
  resource_tags                 = local.shared_tags
  terminate_instance_on_failure = true
  subnet_id                     = var.builder_subnet_id
  security_group_ids            = [var.builder_sg_id]
  key_pair                      = data.aws_key_pair.ec2.key_name
  sns_topic_arn                 = aws_sns_topic.esri_image_builder_sns_topic.arn
  logging {
    s3_logs {
      s3_bucket_name = local.imageBuilderLogBucket
      s3_key_prefix  = "imagebuilder/logs"
    }
  }
  tags = local.shared_tags
}
