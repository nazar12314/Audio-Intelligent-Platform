output "recordings_bucket" {
  description = "AUDIO_STORAGE__BUCKET for the app."
  value       = module.recordings_bucket.name
}

output "app_role_arn" {
  description = "Role the app assumes (local AWS profile role_arn; ECS task role later)."
  value       = module.app_role.arn
}

output "app_env" {
  description = "Lines for the app's .env when running against AWS (`make tf-app-env`)."
  value       = <<-EOT
    AUDIO_AWS__REGION=${var.region}
    AUDIO_AWS__ENDPOINT_URL=
    AUDIO_AWS__S3_ADDRESSING_STYLE=virtual
    AUDIO_STORAGE__BUCKET=${module.recordings_bucket.name}
    AWS_PROFILE=${local.name_prefix}-app
  EOT
}

output "aws_cli_app_profile" {
  description = "Profile to add to ~/.aws/config so the app assumes the least-privilege role."
  value       = <<-EOT
    [profile ${local.name_prefix}-app]
    role_arn = ${module.app_role.arn}
    source_profile = ${local.name_prefix}
    region = ${var.region}
  EOT
}
