terraform {
  backend "s3" {
    # bucket and region come from backend.hcl (git-ignored, written by `make tf-bootstrap`):
    #   terraform init -backend-config=backend.hcl
    key          = "envs/dev/terraform.tfstate"
    encrypt      = true
    use_lockfile = true
  }
}
