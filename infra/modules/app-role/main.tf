# Locally, developers assume this role from their SSO session; on ECS it becomes the task role
# (add "ecs-tasks.amazonaws.com" to trusted_services).

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "trust" {
  dynamic "statement" {
    for_each = length(var.trusted_principal_arn_patterns) > 0 ? [1] : []
    content {
      sid     = "AssumeFromTrustedPrincipals"
      actions = ["sts:AssumeRole", "sts:SetSourceIdentity"]
      principals {
        type        = "AWS"
        identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
      }
      condition {
        test     = "ArnLike"
        variable = "aws:PrincipalArn"
        values   = var.trusted_principal_arn_patterns
      }
    }
  }

  dynamic "statement" {
    for_each = length(var.trusted_services) > 0 ? [1] : []
    content {
      sid     = "AssumeFromServices"
      actions = ["sts:AssumeRole"]
      principals {
        type        = "Service"
        identifiers = var.trusted_services
      }
      condition {
        test     = "StringEquals"
        variable = "aws:SourceAccount"
        values   = [data.aws_caller_identity.current.account_id]
      }
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = var.name
  description          = "Application role: S3 access to audio recordings."
  assume_role_policy   = data.aws_iam_policy_document.trust.json
  max_session_duration = var.max_session_duration_s

  lifecycle {
    precondition {
      condition     = length(var.trusted_principal_arn_patterns) + length(var.trusted_services) > 0
      error_message = "Set trusted_principal_arn_patterns and/or trusted_services: a role nobody can assume is useless."
    }
  }
}

data "aws_iam_policy_document" "recordings" {
  statement {
    sid       = "RecordingsBucket"
    actions   = ["s3:ListBucket"] # HeadBucket (readiness) and 404 (not 403) on missing objects
    resources = [var.recordings_bucket_arn]
  }

  statement {
    sid = "RecordingsObjects"
    actions = [
      "s3:PutObject", # also CreateMultipartUpload, UploadPart, CompleteMultipartUpload
      "s3:GetObject", # also HeadObject
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${var.recordings_bucket_arn}/${var.recordings_key_prefix}*"]
  }

  dynamic "statement" {
    for_each = var.recordings_kms_key_arn == null ? [] : [var.recordings_kms_key_arn]
    content {
      sid       = "RecordingsKms"
      actions   = ["kms:GenerateDataKey", "kms:Decrypt"]
      resources = [statement.value]
    }
  }
}

resource "aws_iam_role_policy" "recordings" {
  name   = "recordings-s3"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.recordings.json
}
