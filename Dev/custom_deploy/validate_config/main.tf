variable "env" {
  type = any
  
  validation {
    condition =  lookup(var.env, "account_id", "") != "" && lookup(var.env, "profile", "") != "" && lookup(var.env, "personal_tag", "") != ""
    error_message = "You must provide values for all of the following in the configuration.yml: account_id, profile, and personal_tag" 
  }
}

output "env" {
    value = var.env
}