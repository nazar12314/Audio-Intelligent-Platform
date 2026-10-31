# AWS infrastructure: Networking

> [Index](../../README.md) · **Use for:** VPC, subnets, NAT, VPC endpoints, security groups, Route 53/ACM/WAF/CloudFront, ALB vs API Gateway. Placeholders are defined in the index.

## 6. Networking

### 6.1 VPC baseline (`modules/network`)

- **Use 3 AZs in prod and 2 in dev.**
- **Subnet tiers:**

  | Tier | Contains | Routing |
  |---|---|---|
  | **public** | ALB, NAT gateways | — |
  | **private-app** | ECS tasks, Lambdas in the VPC | Egress through NAT |
  | **private-data** | RDS, ElastiCache, MSK, MQ | **No** route to the internet |

- Size the CIDRs generously, for example a `/16` per VPC. Non-overlapping CIDRs across
  accounts allow peering or Transit Gateway later.
- **NAT gateways:**
  - Prod gets one per AZ, so that losing one AZ does not cut egress for the others.
  - Dev may use a single NAT gateway to save money.
- **VPC endpoints** cut NAT cost and keep traffic private:
  - Gateway endpoints for **S3** and **DynamoDB** are free. Always add them.
  - Interface endpoints for ECR (api + dkr), CloudWatch Logs, Secrets Manager, SSM, STS,
    SQS, and Bedrock: add those the workload uses.
- **Security groups reference other security groups**, not CIDRs. For example: ALB-SG to
  App-SG on the app port, and App-SG to DB-SG on 5432. Allow no `0.0.0.0/0` ingress except on
  the ALB's 443.
- Turn on **VPC Flow Logs**, sent to CloudWatch or S3 with retention set.

### 6.2 Edge

- **Route 53** for DNS, and **ACM** for TLS certificates. CloudFront certificates must live in
  `us-east-1`.
- **Only TLS reaches the ALB:** port 80 redirects to 443, and an up-to-date TLS security
  policy is applied.
- Put **AWS WAF** on the ALB, CloudFront, or API Gateway, with managed rule groups (common,
  known bad inputs, IP reputation) and rate-based rules.
- Use **CloudFront** for static assets and for global latency. The ALB can be its origin;
  restrict the ALB to CloudFront using the managed prefix list plus a secret header.

### 6.3 ALB versus API Gateway

| Need | Pick |
|---|---|
| Containers on ECS/EKS, WebSockets, SSE, long streaming responses (LLM tokens) | **ALB**. Raise the **idle timeout** above the longest expected gap between stream chunks |
| Lambda backend, per-client API keys and usage plans, request validation at the edge | **API Gateway** (HTTP API by default, REST API for usage plans, WAF, or private APIs) |
| Long-running requests through API Gateway | Avoid them, because integration timeouts are short by default. Return `202` plus a job ID ([architecture §8.5](../../backend-architecture/06-messaging-and-background-jobs.md)) |
