# Platform Architecture

PDP point 6: the assistant as an event-driven, serverless system on GCP.
The CLI/GitHub-Actions mode keeps working unchanged; the services wrap the
same `ai_test_assistant` package as a library.

## Flow

```text
GitHub PR (opened / synchronize / reopened)
      │  webhook, HMAC-signed
      ▼
[webhook-receiver]         Cloud Run, public, scale-to-zero
      │  verifies signature, filters events, publishes job, returns 202
      ▼
[Pub/Sub: pr-analysis-jobs]
      │  push subscription, ack deadline 600s,
      │  5 delivery attempts → pr-analysis-jobs-dead-letter
      ▼
[analysis-worker]          Cloud Run, private (Pub/Sub invoker only), concurrency 1
      │  idempotency check → clone PR head → run pipeline (library call)
      ├────────▶ [GCS artifacts bucket]   reports + generated tests
      └────────▶ [GitHub commit status]   ai-test-assistant: success/failure
```

## Job message contract

Published by the receiver, consumed by the worker (JSON, UTF-8):

```json
{
  "repo_full_name": "olehk334/calculator",
  "clone_url": "https://github.com/olehk334/calculator.git",
  "pr_number": 7,
  "head_sha": "abc123...",
  "base_ref": "main",
  "delivery_id": "github-delivery-guid"
}
```

Idempotency key: `repo_full_name / pr_number / head_sha` — also the GCS
artifact prefix. A job whose JSON report already exists at that prefix is
acknowledged without reprocessing.

## Why this shape

- **Receiver and worker are separate services** because they have opposite
  requirements: the receiver must respond within GitHub's 10-second webhook
  timeout and is public; the worker runs for minutes (clone + LLM + pytest)
  and must not be publicly callable.
- **Pub/Sub between them** decouples intake from processing (queue-based
  load leveling): a burst of PRs queues up instead of overloading workers,
  and Cloud Run scales worker instances with the backlog.
- **Worker concurrency = 1** because the pipeline shells out to git and
  pytest; scaling happens horizontally by instance count, which keeps the
  mental model simple (one job = one container).
- **Push (not pull) subscription** so the worker is a plain HTTP service —
  same programming model as the receiver, no subscriber loop to manage.

## Failure modes

| Failure | What happens |
| --- | --- |
| Invalid webhook signature | Receiver returns 401; nothing queued. |
| Non-PR event / closed PR | Receiver returns 200 "ignored"; nothing queued. |
| Malformed queue message | Worker acks it (200) — retrying can never succeed. |
| Duplicate delivery (Pub/Sub is at-least-once) | Idempotency check finds the report in GCS, acks without reprocessing. |
| Worker crashes mid-job | No ack → Pub/Sub redelivers after the ack deadline; the retry starts clean (idempotency marker is only written on success). |
| LLM/Gemini outage | Pipeline records per-file errors; if the job itself throws, worker returns 500 → up to 5 retries → dead-letter topic. |
| Poison job (always fails) | After 5 attempts lands in `pr-analysis-jobs-dead-letter` for manual inspection. |
| GitHub status post fails | Job still succeeds (artifacts are uploaded); status is best-effort. |

## Environment variables

| Service | Variable | Purpose |
| --- | --- | --- |
| receiver | `GITHUB_WEBHOOK_SECRET` | HMAC secret shared with the GitHub webhook |
| receiver | `PUBSUB_TOPIC` | full topic path to publish jobs to |
| worker | `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` / `GEMINI_MODEL` | Vertex AI settings (read by the assistant's config loader) |
| worker | `DRY_RUN` | `true` = deterministic placeholder responses, no Vertex calls |
| worker | `ARTIFACTS_BUCKET` | GCS bucket; unset = local mode (no upload, no idempotency) |
| worker | `GITHUB_TOKEN` | optional; enables commit statuses |

## Running locally (no cloud needed)

The worker runs standalone in dry-run mode — you POST it a Pub/Sub-shaped
envelope and it clones the (public) repo, runs the pipeline with the
placeholder LLM, and reports:

```bash
cd services/analysis_worker
DRY_RUN=true uvicorn worker_app:app --port 8080
```

```bash
python - <<'EOF'
import base64, json, urllib.request
job = {
    "repo_full_name": "olehk334/calculator",
    "clone_url": "https://github.com/olehk334/calculator.git",
    "pr_number": 1,
    "head_sha": "HEAD",
    "base_ref": "main",
    "delivery_id": "local-test",
}
envelope = {"message": {"data": base64.b64encode(json.dumps(job).encode()).decode()}}
req = urllib.request.Request(
    "http://localhost:8080/pubsub",
    data=json.dumps(envelope).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req).read().decode())
EOF
```

The receiver's signature and filtering logic is covered by unit tests
(`tests/services/`); it needs a real Pub/Sub topic to do anything useful, so
locally it is exercised through the tests rather than run standalone.

## Deployment

`infra/deploy.sh` creates everything (APIs, Artifact Registry, images,
topics, bucket, both Cloud Run services, the push subscription with
dead-lettering) and prints the webhook URL to configure on GitHub.
It creates billable resources — do not run it casually.
