variable "environment" {
  description = "Hydrovis environment"
  type        = string
}

variable "account_id" {
  description = "Hydrovis environment"
  type        = string
}

variable "region" {
  description = "Hydrovis environment"
  type        = string
}

variable "deployment_bucket" {
  description = "S3 buckets where the lambda zip files will live."
  type        = string
}

variable "lambda_role" {
  description = "Role to use for the lambda functions."
  type        = string
}

variable "default_tags" {
  type = map(string)
}

variable "lambda_name" {
  type = string
}

variable "ecr_repository_image_tag" {
  type = string
}

variable "profile" {
  type = string
}