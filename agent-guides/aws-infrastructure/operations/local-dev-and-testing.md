# AWS infrastructure: Local development and testing against AWS

> [Index](../../README.md) · **Use for:** AWS settings in the app, boto3/aioboto3, moto, LocalStack. Placeholders are defined in the index.
> **Related:** [11-testing](../../backend-architecture/11-testing.md)

## 16. Local development and testing against AWS

- **The app's AWS settings group:**
  - `<APP>_AWS__REGION`, plus an optional `<APP>_AWS__ENDPOINT_URL` (or the SDK-standard
    `AWS_ENDPOINT_URL`) that points to LocalStack.
  - The app never takes access keys as settings: it uses the default credential chain, which
    on AWS means the task role.
- **SDK:** `boto3` in sync code or a thread pool. Use `aioboto3` / `aiobotocore` in async
  services. Create the clients once in the container and reuse them. Set explicit timeouts and
  the `botocore` retry mode to `standard` or `adaptive`.
- **Unit tests:** `moto` (`mock_aws`) for adapter logic; fakes for services (as in the
  template).
- **Integration tests:** **LocalStack** (as a compose service under the `aws` profile, or via
  testcontainers) for S3, SQS, SNS, DynamoDB, Secrets Manager, and similar. Mark them
  `@pytest.mark.integration`.
- **Bedrock / SageMaker** have no local emulator. Use the fake `LLMClient` in tests, and run a
  small, opt-in smoke test against a real dev account.
- Never point local development or tests at production resources.
