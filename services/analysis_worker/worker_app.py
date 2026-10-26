"""Analysis worker: consumes PR jobs from Pub/Sub and runs the assistant.

Receives Pub/Sub *push* messages, clones the PR head, runs the existing
``ai_test_assistant`` pipeline as a library, uploads artifacts to GCS, and
posts a commit status back to GitHub.

One file per concern: job_message.py (the message contract), analysis_job.py
(what one job does), artifact_store.py (Cloud Storage), commit_status.py
(GitHub), worker_metrics.py (Prometheus). This file is the HTTP side.

Response codes drive the queue semantics:
    200  job done or safely skipped        -> message acknowledged
    500  processing failed                 -> Pub/Sub retries, then dead-letters

Environment:
    GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / GEMINI_MODEL / DRY_RUN
                       read by the assistant's config loader
    ARTIFACTS_BUCKET   GCS bucket for reports and generated tests (optional:
                       unset = local mode, no upload and no idempotency check)
    GITHUB_TOKEN       token for commit statuses (optional: unset = no status)
    LLM_CACHE_POLICY   response cache eviction: lru (default) or lfu

Run with Cloud Run concurrency=1: the pipeline shells out to pytest and git,
so scaling happens by adding instances, not threads.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from typing import Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from ai_test_assistant.cache import LFUCache, LRUCache

from analysis_job import run_analysis_job
from artifact_store import report_already_uploaded
from job_message import AnalysisJob, MalformedJob, decode_pubsub_push
from worker_metrics import JOB_DURATION, JOBS_PROCESSED, record_cache_lookups

app = FastAPI(title="ai-test-assistant analysis worker")


def response_cache_from_env() -> LRUCache | LFUCache:
    policy = (os.environ.get("LLM_CACHE_POLICY") or "lru").strip().lower()
    if policy == "lru":
        return LRUCache(capacity=256)
    if policy == "lfu":
        return LFUCache(capacity=256)
    raise ValueError(f"LLM_CACHE_POLICY must be 'lru' or 'lfu', not {policy!r}")


# Process-lifetime cache shared across jobs: a re-pushed branch with unchanged
# files sends byte-identical prompts, which this turns into free cache hits.
RESPONSE_CACHE = response_cache_from_env()
# Export the policy's cache series from the start: dashboards then show 0, not "no data".
record_cache_lookups(RESPONSE_CACHE.policy, hits=0, misses=0)

# One job per process, as on Cloud Run (concurrency=1). Sync endpoints run in a
# thread pool, the response cache is not thread-safe, and a duplicate delivery
# must find the first job's report before it decides whether to skip.
_ONE_JOB_AT_A_TIME = threading.Lock()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def _run_job_once(job: AnalysisJob) -> Response:
    if report_already_uploaded(job):
        JOBS_PROCESSED.labels(status="skipped").inc()
        return Response(
            status_code=200,
            content=f"skipped: {job.artifact_prefix} already processed",
        )

    try:
        with JOB_DURATION.time():
            result = run_analysis_job(job, RESPONSE_CACHE)
    except Exception as exc:  # noqa: BLE001 - let Pub/Sub retry, then dead-letter
        JOBS_PROCESSED.labels(status="failed").inc()
        # Pub/Sub discards the response body, so the reason must be logged
        # here or it is invisible to operators.
        print(
            f"error: job {job.artifact_prefix} failed: {exc}",
            file=sys.stderr,
        )
        return Response(status_code=500, content=f"processing failed: {exc}")

    JOBS_PROCESSED.labels(status="processed").inc()
    return Response(
        status_code=200,
        content=json.dumps(
            {
                "processed": job.artifact_prefix,
                "files": len(result.file_results),
            }
        ),
        media_type="application/json",
    )


@app.post("/pubsub")
def handle_pubsub_push(envelope: dict[str, Any]) -> Response:
    try:
        job = decode_pubsub_push(envelope)
    except MalformedJob as exc:
        # Retrying a malformed message can never succeed; ack it away.
        JOBS_PROCESSED.labels(status="ignored").inc()
        return Response(status_code=200, content=f"ignored: {exc}")

    with _ONE_JOB_AT_A_TIME:
        return _run_job_once(job)
