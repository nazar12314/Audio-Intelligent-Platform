# This root keeps local state (terraform.tfstate, git-ignored): it creates the remote backend
# everything else uses. If the state file is lost, re-import the resources; nothing is recreated.

locals {
  name_prefix = "${var.project}-${var.environment}"
}

module "state_bucket" {
  source = "../modules/s3-bucket"

  name                               = "${var.project}-tfstate-${var.account_id}"
  noncurrent_version_expiration_days = 90 # state history for recovery
}

module "account_baseline" {
  source = "../modules/account-baseline"

  name_prefix         = local.name_prefix
  monthly_budget_usd  = var.monthly_budget_usd
  budget_alert_emails = var.budget_alert_emails
}
