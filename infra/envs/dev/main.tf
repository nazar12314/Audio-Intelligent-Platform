# PostgreSQL is intentionally absent: it stays in docker compose until the app is deployed to AWS
# (docs/adr/0003).

locals {
  name_prefix = "${var.project}-${var.environment}"
}

module "recordings_bucket" {
  source = "../../modules/s3-bucket"

  name                               = "${local.name_prefix}-recordings-${var.account_id}"
  cors_allowed_origins               = var.cors_allowed_origins
  noncurrent_version_expiration_days = 30
  abort_incomplete_multipart_days    = 7
}

module "app_role" {
  source = "../../modules/app-role"

  name                  = "${local.name_prefix}-app"
  recordings_bucket_arn = module.recordings_bucket.arn
  # Any IAM Identity Center (SSO) role in this account may assume it for local development.
  trusted_principal_arn_patterns = [
    "arn:aws:iam::${var.account_id}:role/aws-reserved/sso.amazonaws.com/*",
  ]
}
