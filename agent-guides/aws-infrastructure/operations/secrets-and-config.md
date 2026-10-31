# AWS infrastructure: Secrets and configuration

> [Index](../../README.md) · **Use for:** Secrets Manager, SSM, injecting env vars into tasks, KMS. Placeholders are defined in the index.

## 12. Secrets and configuration

- **Secrets Manager** holds secrets: DB credentials, API keys, JWT signing keys. Turn on
  rotation where it is supported (RDS-managed credentials rotate on their own).
- **SSM Parameter Store** holds non-secret config. Use SecureString only for low-value secrets.
- **How values reach the app:** the ECS task definition maps them into the **same env vars
  the app already reads**, for example `<APP>_POSTGRES__DSN` and `<APP>_JWT_SECRET`:
  - `secrets` with `valueFrom: <secret-arn>[:json-key::]` for secrets;
  - `environment` for plain values, which come from Terraform outputs.

  The app keeps reading only env vars ([architecture §4.1](../../backend-architecture/02-core-config-di-errors-lifecycle.md)). Fetch secrets at
  runtime from code only when rotation without a restart is required, and then cache them
  with a TTL.
- **Which role reads what:**
  - The **task execution role** reads the secrets and pulls the image at startup.
  - The **task role** is what the app's own AWS SDK calls use, scoped to specific ARNs.
- Use **KMS customer-managed keys** for regulated data, with key policies per environment.
  Leave key rotation on.
- No secrets in images, Terraform state, CI logs, or task-definition plain `environment`
  values.
