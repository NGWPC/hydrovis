###########################################################
###########################################################
#####  START STATIC CONFIGURATION: DO NOT EDIT BELOW  #####
###########################################################
###########################################################
variable "viz_role" {
    type = string
}

variable "lambda_functions" {
    type = map
}

variable "step_functions" {
    type = map
}

variable "s3_buckets" {
    type = map
}

variable "cloudwatch_log_groups" {
    type = map
}

variable "secrets" {
    type = map
}

variable "batch_job_definitions" {
    type = map
}

variable "batch_job_queues" {
    type = map
}

variable "region" {
    type = string
}

variable "viz_db_host" {
    type = string
    default = "rds-viz.hydrovis.internal"
}

variable "viz_db_name" {
    type = string
    default = "vizprocessing"
}

variable "egis_db_host" {
    type = string
    default = "rds-egis.hydrovis.internal"
}

variable "egis_db_name" {
    type = string
    default = "hydrovis"
}

variable "wrds_db_host" {
    type = string
    default = "rds-ingest.hydrovis.internal"
}

variable "wrds_db_dump_sns" {
    type = string
    default = "not_needed"
}

variable "nwm_dataflow_version" {
    type = string
}

variable "fim_version" {
    type = string
    default = "placeholder"
}

variable "hand_version" {
    type = string
    default = "undefined"
}

variable "deploy_resources" {
    type = map(bool)
}

variable "egis_portal_password" {
    type = string
    default = "placeholder"
}

variable "personal_tag" {
    type = string
}

variable "profile" {
    type = string
}

variable "account_id" {
    type = string
}

variable "default_tags" {
    type = map(string)
}
#########################################################
#########################################################
#####  END STATIC CONFIGURATION: DO NOT EDIT ABOVE  #####
#########################################################
#########################################################