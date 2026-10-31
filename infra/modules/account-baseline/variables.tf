variable "name_prefix" {
  description = "Prefix for resource names, e.g. <project>-<env>."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget in USD; alerts at 50/80/100% actual and 100% forecasted."
  type        = number

  validation {
    condition     = var.monthly_budget_usd > 0
    error_message = "Budget must be positive."
  }
}

variable "budget_alert_emails" {
  description = "Email addresses that receive budget alerts."
  type        = list(string)

  validation {
    condition     = length(var.budget_alert_emails) > 0
    error_message = "At least one alert email is required."
  }
}
