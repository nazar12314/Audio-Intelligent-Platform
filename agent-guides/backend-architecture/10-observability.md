# Backend architecture: Observability

> [Index](../README.md) · **Use for:** logging, request IDs, metrics, tracing, health endpoints. Placeholders are defined in the index.
> **Related:** [security-and-observability](../aws-infrastructure/operations/security-and-observability.md)

## 12. Observability

- **Logging:**
  - Structured JSON on stdout, one event per line. Text output is for dev only.
  - Every log line carries `request_id` / `correlation_id`, plus `user_id` when known.
  - The request ID is taken from the inbound `X-Request-ID` header, or generated. It is
    returned in the response and **propagated** into outbound HTTP headers and event
    envelopes.
- **Event codes:** business events are logged with stable codes (enums), not with free text.
- **Redaction:** a single helper masks secrets, tokens, passwords and credentialed URLs.
  Prompts and model outputs are logged only at debug level, and only in non-production
  environments, because they can contain personal data.
- **Metrics** (Prometheus at `/metrics`, toggled by a setting):
  - RED metrics per route (rate, errors, duration);
  - per dependency: latency, errors, circuit state;
  - queue depth and consumer lag;
  - cache hit ratio;
  - LLM tokens and cost;
  - event-loop lag.
- **Tracing:** OpenTelemetry instrumentation for FastAPI, httpx, the database drivers, Redis,
  and the brokers. Trace context travels in message headers. The exporter endpoint is
  configured through settings; where traces end up is a deployment concern.
- **Health:**
  - `GET /health/live` reports only that the process is up, with no dependency checks.
  - `GET /health/ready` checks each **required** dependency under a short timeout and returns
    503 with details when one fails. Optional dependencies are reported as `degraded` but do
    not fail readiness.
