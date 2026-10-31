variable "name" {
  description = "Globally unique bucket name, e.g. <project>-<env>-<purpose>-<account_id>."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.name))
    error_message = "Must be a valid S3 bucket name (3-63 chars, lowercase, digits, dots, hyphens)."
  }
}

variable "kms_key_arn" {
  description = "KMS key for SSE-KMS (with bucket key). null uses SSE-S3."
  type        = string
  default     = null
}

variable "noncurrent_version_expiration_days" {
  description = "Days after which noncurrent object versions are deleted."
  type        = number
  default     = 30
}

variable "abort_incomplete_multipart_days" {
  description = "Days after which incomplete multipart uploads are aborted (their parts cost storage)."
  type        = number
  default     = 7
}

variable "intelligent_tiering_after_days" {
  description = "Move current objects to S3 Intelligent-Tiering after this many days. null disables the transition."
  type        = number
  default     = null
}

variable "cors_allowed_origins" {
  description = "Browser origins allowed to PUT/GET objects via presigned URLs. Empty disables CORS."
  type        = list(string)
  default     = []
}
