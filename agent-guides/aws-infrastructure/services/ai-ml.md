# AWS infrastructure: AI / ML services

> [Index](../../README.md) · **Use for:** Bedrock, SageMaker training/endpoints/MLOps, EDA tools. Placeholders are defined in the index.
> **Related:** [07-external-apis-llm-rag](../../backend-architecture/07-external-apis-llm-rag.md)

## 10. AI / ML services

### 10.1 Bedrock (managed LLMs and embeddings): the default for LLM features

- Call it through the `LLMClient` / `EmbeddingClient` adapters (`adapters/bedrock.py`). Model
  IDs live in settings.
- Use the **bedrock-runtime VPC interface endpoint**, so traffic does not go through NAT. The
  IAM policy allows `bedrock:InvokeModel*` only on the specific model ARNs (or inference
  profiles) the app uses.
- Request model access in each account and region (dev, staging, prod) as an explicit IaC or
  runbook step. Use **cross-region inference profiles** for higher throughput where data
  residency allows.
- Turn on **Bedrock Guardrails** for content filtering or PII redaction when requirements
  call for it.
- Log token usage to metrics. Watch the throttling quotas, and request increases before
  launch.
- **Bedrock Knowledge Bases** offer managed RAG ([aws §8.5](data-stores.md)). **Bedrock Agents** offer managed
  tool-calling. Choose them only when their limits suit the project.

### 10.2 SageMaker: custom or self-hosted models

**Endpoint and inference options:**

| Need | Pick |
|---|---|
| Instant, always-on predictions | **Real-time endpoint** |
| Intermittent traffic where a cold start is acceptable | **Serverless endpoint** (scales to zero) |
| Large payloads or long processing (documents, images) | **Async endpoint**: the request is queued and the result is written to S3 |
| Offline predictions over a whole dataset | **Batch Transform**: no persistent endpoint, cheapest for one-off bulk |
| Safe rollout or A/B testing of a new model | **Production variants** with traffic weights (for example 90/10) on one endpoint |
| Detecting data drift or quality drift in production | **Model Monitor** |

**Training and MLOps:**

- **Training Jobs:** managed, ephemeral compute that writes the model to S3.
  - **File mode** downloads the data first. It is simple, and best for small data.
  - **Pipe mode** (or FastFile) streams the data from S3. It starts faster and needs less
    disk, which suits large datasets.
  - Train directly from **EFS** or **FSx for Lustre** to avoid moving data repeatedly ([aws §9.3](storage.md)).
- **Automatic Model Tuning:** hyperparameter optimization, Bayesian by default.
- **Debugger:** detects training problems (overfitting, vanishing or exploding gradients) and
  can stop the job. **Clarify:** bias detection and explainability.
- **Pipelines:** automated workflows (process → train → evaluate → register → deploy).
  **Model Registry:** model versions, approval, rollback. **Experiments:** compare runs.
- **Feature Store:** shared features, with an **online** store for low-latency inference and
  an **offline** store for training.
- **Data prep:** Data Wrangler, now inside Canvas, is visual data prep for data scientists.
  **Canvas** is no-code end-to-end ML for business users. **Autopilot** is AutoML.

### 10.3 Exploratory data analysis

| Tool | Use for |
|---|---|
| SageMaker Studio / notebooks | Python exploration and visualization |
| Athena | Quick SQL over data in S3 |
| QuickSight | Dashboards for non-technical users |
| Glue DataBrew | Visual profiling and cleaning, no code |
| EMR + Spark | Exploring very large datasets |
