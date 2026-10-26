# 8. PDP · Distributed Systems & Cloud Architecture {#en-cloud}

## In plain words

A distributed system is several programs on several machines that together do one job. The hard part is that any of them can be slow, restart or receive the same message twice. The cloud mode of this project is a small but complete example: a public receiver that answers GitHub in milliseconds, a queue that remembers the work, and a private worker that takes minutes per job. Each piece can fail on its own without losing a job.

![The cloud mode, end to end.](images/platform.en.png)

## Theory in brief

- **Microservices** split a system where requirements conflict. The receiver must answer within GitHub's 10-second webhook timeout and be reachable from the internet; the worker runs for minutes and must not be reachable at all. Different needs, different services. The rule worth remembering: split along conflicting requirements, not along nouns.
- **Event-driven systems** connect services through messages instead of calls. The producer puts a message on a topic and moves on; consumers take it when they can. Queues deliver *at least once*, so a consumer must be **idempotent**: processing the same message twice must have the same effect as once.
- **Serverless** means the platform runs your container only when there is work and scales it to zero in between. Services must be stateless; everything that matters lives in storage or in the queue. Cold starts (100 ms to seconds) are the price.
- **Scalability patterns used here:** queue-based load levelling (bursts wait in the queue instead of overloading workers), horizontal scaling (more instances, each handling one job), bounded retries with a **dead-letter queue** for messages that always fail, and the idempotency key that makes retries safe.
- **Cloud platforms.** The same shapes exist everywhere:

| Role | GCP (used) | AWS | Azure |
| --- | --- | --- | --- |
| Run containers, scale to zero | Cloud Run | App Runner / Lambda | Container Apps |
| Queue between services | Pub/Sub | SNS + SQS | Service Bus |
| Dead letters | Pub/Sub dead-letter topic | SQS dead-letter queue | Service Bus dead-letter queue |
| Artifact storage | Cloud Storage | S3 | Blob Storage |
| Service-to-service auth | IAM + OIDC push | IAM roles | Managed Identity |
| Managed LLM | Vertex AI | Bedrock | Azure OpenAI |

## How this project applies it

**Receiver** (`services/webhook_receiver/`, one file): verify the HMAC signature with the shared secret, keep only `pull_request` events with action opened / synchronize / reopened, publish a five-field job (`repo_full_name`, `clone_url`, `pr_number`, `head_sha`, `base_ref`) and answer 202. Anything else is 401 or "ignored".

**Queue:** one Pub/Sub topic with a push subscription to the worker, a 600-second ack deadline, five delivery attempts, then a dead-letter topic with its own pull subscription for inspection.

**Worker** (`services/analysis_worker/`, six files, one per concern): the HTTP side, the job message, the job itself (clone → pipeline → metrics → upload → commit status), Cloud Storage, GitHub status, Prometheus metrics. It answers 200 to acknowledge a message and 500 to make Pub/Sub retry. A malformed message is acknowledged at once, because retrying it can never succeed.

**Idempotency:** the key is `repo/pr/sha`, which is also the folder in Cloud Storage. A job whose JSON report already exists at that path is skipped. The marker is written only on success, so a job that crashed half-way is simply redone.

**One job at a time:** Cloud Run runs the worker with concurrency 1, and the worker holds a lock around each job, because the pipeline shells out to git and pytest. Scaling means more instances. The endpoints are plain functions in a thread pool, so `/health` and `/metrics` keep answering during a job (measured: 27 ms instead of 1.6 s with the earlier async design).

**Verified locally with the Pub/Sub emulator:** a signed webhook was queued, pushed and processed; a job with a non-existent base branch failed five times and landed in the dead-letter topic; the worker's failed-job counter rose from 1 to 6.

**Deployment:** `infra/deploy.sh` creates everything with `gcloud`: APIs, Artifact Registry, both images via Cloud Build, topics, bucket, both Cloud Run services, the push subscription with its service account, and the IAM grants the dead-letter path needs. It is run on purpose; it creates billable resources.

## Likely questions

**Q:** Why push delivery and not a worker that pulls from the queue?

**A:** With push, the worker is a plain HTTP service like the receiver: same programming model, scaled by the platform, no subscriber loop to keep alive. Pull would be better for very long jobs or strict rate control.

**Q:** What if two deliveries of the same job overlap?

**A:** They cannot overlap in one instance (the lock), and across instances the second one finds the report in Cloud Storage and skips. The window where both run is small and only wastes work; it cannot corrupt the result, because each job writes to its own `repo/pr/sha` folder.

**Q:** Why does the receiver have no metrics?

**A:** It does one cheap thing, and Cloud Run already reports request count, latency and errors for it. Custom metrics belong where custom logic is: the worker.
