variable "account_id" {
  description = "AWS account ID this configuration may touch (provider allowed_account_ids)."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Must be a 12-digit AWS account ID."
  }
}

variable "region" {
  description = "Primary AWS region."
  type        = string
  default     = "eu-central-1"
}

variable "project" {
  description = "Short project name used in resource names and tags."
  type        = string
  default     = "audio-platform"
}

variable "owner" {
  description = "Owner tag: person or team responsible for the resources."
  type        = string
}
