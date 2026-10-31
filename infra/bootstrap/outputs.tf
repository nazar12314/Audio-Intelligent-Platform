output "state_bucket" {
  description = "Remote state bucket for every other root in this account."
  value       = module.state_bucket.name
}

output "backend_config" {
  description = "Content for envs/<env>/backend.hcl (written by `make tf-bootstrap`)."
  value       = <<-EOT
    bucket = "${module.state_bucket.name}"
    region = "${var.region}"
  EOT
}
