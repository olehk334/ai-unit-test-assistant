# Cloud Platform Equivalence (GCP / AWS / Azure)

The platform is built on GCP. This table maps each building block to its
AWS and Azure equivalents, so the architecture transfers between clouds —
the theory half of PDP point 6.

| Role in this project | GCP (used) | AWS | Azure |
| --- | --- | --- | --- |
| Run the receiver/worker containers, scale to zero | Cloud Run | App Runner (or Lambda w/ container images) | Container Apps |
| Queue between intake and processing | Pub/Sub | SNS + SQS (fan-out + queue) | Service Bus Topics |
| Dead-letter for poison messages | Pub/Sub dead-letter topic | SQS dead-letter queue | Service Bus dead-letter queue |
| Artifact storage (reports, generated tests) | Cloud Storage | S3 | Blob Storage |
| Container images | Artifact Registry | ECR | Container Registry |
| Build images from source | Cloud Build | CodeBuild | ACR Tasks / Pipelines |
| Service-to-service auth (Pub/Sub → worker) | IAM + OIDC push auth | IAM roles + SQS→Lambda event source | Managed Identity |
| Metrics backend (Phase 3, cloud path) | Managed Service for Prometheus | Amazon Managed Prometheus | Azure Monitor managed Prometheus |
| LLM API | Vertex AI (Gemini) | Bedrock | Azure OpenAI |

## The four theory topics, as this project demonstrates them

**Microservices.** Two services split along a real fault line: the receiver
is public, latency-bound (GitHub's 10 s webhook timeout) and trivial; the
worker is private, minutes-long and heavy. They share no code or state —
only the JSON job contract. That is the criterion worth generalizing:
split where requirements conflict, not by noun.

**Event-driven systems.** The webhook is the event source; Pub/Sub carries
the event; the worker reacts to it. Delivery is at-least-once, so the
consumer is idempotent (GCS marker keyed by repo/PR/SHA). Ordering is not
assumed — jobs for different SHAs are independent by design.

**Serverless design.** Both services are stateless containers that scale to
zero; all state lives in the queue and the bucket. The process-lifetime LLM
response cache is an optimization, not state the system depends on — losing
an instance loses nothing but warm cache.

**Scalability patterns.** Queue-based load leveling (bursts queue up instead
of overloading), horizontal scaling (concurrency=1, more instances instead of
more threads), retry with backoff and a bounded attempt count, dead-letter
isolation of poison messages, and idempotent consumers making retries safe.
