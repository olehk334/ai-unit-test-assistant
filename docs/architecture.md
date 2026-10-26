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
  "base_ref": "main"
}
```

Idempotency key: `repo_full_name / pr_number / head_sha` — also the GCS
artifact prefix. A job whose JSON report already exists at that prefix is
acknowledged without reprocessing. The worker ignores fields it does not
know, so messages from an older receiver still decode.

## Code map

One file per concern, so a failing dependency points at one file.

| File | Responsibility |
| --- | --- |
| `services/webhook_receiver/receiver_app.py` | verify HMAC → filter PR events → publish job → 202 |
| `services/analysis_worker/worker_app.py` | HTTP: `/pubsub`, `/health`, `/metrics`; Pub/Sub ack (200) or retry (500) |
| `services/analysis_worker/job_message.py` | the job contract: `AnalysisJob`, decoding, `MalformedJob` |
| `services/analysis_worker/analysis_job.py` | one job: clone → pipeline → metrics → upload → commit status |
| `services/analysis_worker/artifact_store.py` | Cloud Storage: idempotency check and artifact upload |
| `services/analysis_worker/commit_status.py` | GitHub commit status (best effort) |
| `services/analysis_worker/worker_metrics.py` | Prometheus metrics (see [monitoring.md](monitoring.md)) |

The core package runs the same eight steps for the CLI and the worker;
`ai_test_assistant/pipeline.py` calls them in order:

| Step | Module | Output |
| --- | --- | --- |
| 1. What changed? | `changed_files.py` | changed production `.py` files and lines |
| 2. In which order? | `import_graph.py` | dependencies first, import cycles listed |
| 3. What needs tests? | `test_targets.py` | public functions and methods the diff touched |
| 4. What tests exist? | `test_finder.py` | related test files |
| 5. Ask Gemini | `llm_client.py`, `prompts.py`, `cache.py` | test module text (cached by prompt) |
| 6. Do the tests pass? | `test_generator.py`, `llm_test_code.py`, `pytest_runner.py` | ask → validate → write → pytest → repair |
| 7. Old tests outdated? | `suggested_updates.py` | suggested rewrites under `reports/suggested-tests/` |
| 8. What happened? | `report.py` | `ai-test-report.md` and `.json` |

`config.py`, `models.py` and `repo_paths.py` hold the settings, the data
passed between steps, and the shared path rules.

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
- **Plain (non-async) endpoints**: FastAPI runs them in its thread pool, so
  `/health` and `/metrics` answer while a job runs. A lock keeps one job per
  process, the same rule Cloud Run's concurrency = 1 enforces.
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
| Base branch cannot be diffed (deleted, not fetched) | The job fails with git's error (500) instead of reporting "no changes"; retries, then dead-letter. |
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
| worker | `LLM_CACHE_POLICY` | response cache eviction: `lru` (default) or `lfu` |

## Running locally (no cloud needed)

The worker runs standalone in dry-run mode — you POST it a Pub/Sub-shaped
envelope and it clones the (public) repo, runs the pipeline with the
placeholder LLM, and reports:

```bash
cd services/analysis_worker
DRY_RUN=true uvicorn worker_app:app --port 8080
```

Then, from the repository root in a second terminal:

```bash
python monitoring/send_test_job.py \
  --clone-url https://github.com/olehk334/calculator.git \
  --repo-full-name olehk334/calculator
```

The receiver's signature and filtering logic is covered by unit tests
(`tests/services/`); it needs a real Pub/Sub topic to do anything useful, so
locally it is exercised through the tests rather than run standalone.

## Deployment

`infra/deploy.sh` creates everything (APIs, Artifact Registry, images,
topics, bucket, both Cloud Run services, the push subscription with
dead-lettering) and prints the webhook URL to configure on GitHub.
It creates billable resources — do not run it casually.
