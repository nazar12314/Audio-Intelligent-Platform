variable "name" {
  description = "Role name, e.g. <project>-<env>-app."
  type        = string
}

variable "trusted_principal_arn_patterns" {
  description = "ARN patterns (ArnLike) of IAM principals in this account allowed to assume the role, e.g. SSO roles."
  type        = list(string)
  default     = []
}

variable "trusted_services" {
  description = "AWS service principals allowed to assume the role, e.g. [\"ecs-tasks.amazonaws.com\"]."
  type        = list(string)
  default     = []
}

variable "max_session_duration_s" {
  description = "Maximum session duration. Presigned URLs stop working when the signing session expires."
  type        = number
  default     = 3600
}

variable "recordings_bucket_arn" {
  description = "ARN of the audio recordings bucket."
  type        = string
}

variable "recordings_key_prefix" {
  description = "Key prefix the app may read and write (matches object_key_for in the recordings domain)."
  type        = string
  default     = "users/"
}

variable "recordings_kms_key_arn" {
  description = "KMS key of the recordings bucket when it uses SSE-KMS; null for SSE-S3."
  type        = string
  default     = null
}
