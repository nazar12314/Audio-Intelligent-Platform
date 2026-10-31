variable "environment" {
  description = "Environment this account hosts."
  type        = string
  default     = "dev"
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget for the account, USD."
  type        = number
  default     = 20
}

variable "budget_alert_emails" {
  description = "Email addresses that receive budget alerts."
  type        = list(string)
}
