variable "environment" {
  description = "Environment name."
  type        = string
  default     = "dev"
}

variable "cors_allowed_origins" {
  description = "Frontend origins allowed to upload directly to the recordings bucket."
  type        = list(string)
  default     = ["http://localhost:5173"]
}
