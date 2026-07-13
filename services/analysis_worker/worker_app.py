"""Analysis worker: consumes PR jobs from Pub/Sub and runs the assistant.

Receives Pub/Sub *push* messages, clones the PR head, runs the existing
``ai_test_assistant`` pipeline as a library, uploads artifacts to GCS, and
posts a commit status back to GitHub.

Response codes drive the queue semantics:
    200  job done or safely skipped        -> message acknowledged
    500  processing failed                 -> Pub/Sub retries, then dead-letters

Environment:
    GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION / GEMINI_MODEL / DRY_RUN
                       read by the assistant's config loader
    ARTIFACTS_BUCKET   GCS bucket for reports and generated tests (optional:
                       unset = local mode, no upload and no idempotency check)
    GITHUB_TOKEN       token for commit statuses (optional: unset = no status)

Run with Cloud Run concurrency=1: the pipeline shells out to pytest and git,
so scaling happens by adding instances, not threads.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

from ai_test_assistant.cache import LRUCache
from ai_test_assistant.config import load_config
from ai_test_assistant.llm_client import LlmClient, LlmUsageStats
from ai_test_assistant.models import PipelineResult
from ai_test_assistant.pipeline import run_pr_assistant

app = FastAPI(title="ai-test-assistant analysis worker")

# Process-lifetime cache shared across jobs: a re-pushed branch with unchanged
# files sends byte-identical prompts, which this turns into free cache hits.
RESPONSE_CACHE = LRUCache(capacity=256)

JOBS_PROCESSED = Counter(
    "jobs_processed_total", "Analysis jobs by outcome", ["status"]
)
JOB_DURATION = Histogram(
    "job_duration_seconds",
    "End-to-end job duration (clone + pipeline + upload)",
    buckets=(5, 15, 30, 60, 120, 300, 600),
)
LLM_CALLS = Counter("llm_calls_total", "LLM generate calls (cache misses)")
LLM_SECONDS = Counter("llm_seconds_total", "Seconds spent waiting on the LLM")
LLM_PROMPT_TOKENS = Counter("llm_prompt_tokens_total", "Prompt tokens sent")
LLM_RESPONSE_TOKENS = Counter("llm_response_tokens_total", "Response tokens received")
CACHE_HITS = Counter("llm_cache_hits_total", "LLM response cache hits")
CACHE_MISSES = Counter("llm_cache_misses_total", "LLM response cache misses")
GENERATED_FILES = Counter(
    "generated_test_files_total", "Generated test files by pytest outcome", ["result"]
)


class MalformedJob(ValueError):
    """Message cannot ever be processed; ack it instead of retrying forever."""


def decode_pubsub_push(envelope: dict[str, Any]) -> dict[str, Any]:
    message = envelope.get("message")
    if not isinstance(message, dict) or "data" not in message:
        raise MalformedJob("missing message.data in Pub/Sub envelope")
    try:
        payload = base64.b64decode(message["data"])
        job = json.loads(payload)
    except (binascii.Error, ValueError) as exc:
        raise MalformedJob(f"undecodable job payload: {exc}") from exc

    required = {"repo_full_name", "clone_url", "pr_number", "head_sha", "base_ref"}
    missing = required - job.keys()
    if missing:
        raise MalformedJob(f"job missing fields: {sorted(missing)}")
    return job


def artifact_prefix(job: dict[str, Any]) -> str:
    return f"{job['repo_full_name']}/{job['pr_number']}/{job['head_sha']}"


def report_already_uploaded(job: dict[str, Any]) -> bool:
    """Idempotency check: a finished job left its JSON report in GCS."""
    bucket_name = os.environ.get("ARTIFACTS_BUCKET")
    if not bucket_name:
        return False
    from google.cloud import storage

    blob = storage.Client().bucket(bucket_name).blob(
        f"{artifact_prefix(job)}/reports/ai-test-report.json"
    )
    return blob.exists()


def _clone_url_with_token(clone_url: str) -> str:
    """Inject GITHUB_TOKEN into GitHub HTTPS URLs so private repos clone."""
    token = os.environ.get("GITHUB_TOKEN")
    if token and clone_url.startswith("https://github.com/"):
        return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return clone_url


def clone_pr_head(job: dict[str, Any], workdir: Path) -> Path:
    clone_dir = workdir / "repo"
    try:
        subprocess.run(
            ["git", "clone", "--quiet", _clone_url_with_token(job["clone_url"]),
             str(clone_dir)],
            check=True,
            timeout=120,
            capture_output=True,
        )
        # PR refs also cover heads pushed from forks, which a plain clone lacks.
        subprocess.run(
            ["git", "-C", str(clone_dir), "fetch", "--quiet", "origin",
             f"pull/{job['pr_number']}/head"],
            check=False,
            timeout=120,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "checkout", "--quiet", job["head_sha"]],
            check=True,
            timeout=60,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        # Re-raise without exc.cmd: the clone URL may embed the token.
        raise RuntimeError(
            f"git failed (exit {exc.returncode}) preparing "
            f"{job['repo_full_name']}@{job['head_sha']}"
        ) from None
    return clone_dir


async def run_assistant_on_clone(
    job: dict[str, Any], clone_dir: Path
) -> tuple[PipelineResult, LlmUsageStats]:
    config = load_config(
        repo_root=clone_dir,
        cli_overrides={"base_ref": f"origin/{job['base_ref']}"},
    )
    llm = LlmClient(config, response_cache=RESPONSE_CACHE)
    result = await run_pr_assistant(config, llm=llm)
    return result, llm.usage


class CacheDeltaCounter:
    """Turn the shared cache's cumulative hit/miss counts into per-job deltas
    for Prometheus counters. Correct under the worker's concurrency=1 model;
    concurrent jobs would need a lock around ``take``."""

    def __init__(self, cache: LRUCache):
        self._cache = cache
        self._seen_hits = 0
        self._seen_misses = 0

    def take(self) -> tuple[int, int]:
        hit_delta = self._cache.hits - self._seen_hits
        miss_delta = self._cache.misses - self._seen_misses
        self._seen_hits = self._cache.hits
        self._seen_misses = self._cache.misses
        return hit_delta, miss_delta


CACHE_DELTAS = CacheDeltaCounter(RESPONSE_CACHE)


def record_job_metrics(result: PipelineResult, usage: LlmUsageStats) -> None:
    LLM_CALLS.inc(usage.calls)
    LLM_SECONDS.inc(usage.total_seconds)
    LLM_PROMPT_TOKENS.inc(usage.prompt_tokens)
    LLM_RESPONSE_TOKENS.inc(usage.response_tokens)

    hit_delta, miss_delta = CACHE_DELTAS.take()
    CACHE_HITS.inc(hit_delta)
    CACHE_MISSES.inc(miss_delta)

    for file_result in result.file_results:
        if file_result.generated_test_file is not None:
            outcome = "passed" if file_result.status == "passed" else "failed"
            GENERATED_FILES.labels(result=outcome).inc()


def upload_artifacts(job: dict[str, Any], clone_dir: Path) -> str | None:
    """Upload reports and generated tests to GCS; return the GCS prefix URL."""
    bucket_name = os.environ.get("ARTIFACTS_BUCKET")
    if not bucket_name:
        return None
    from google.cloud import storage

    bucket = storage.Client().bucket(bucket_name)
    prefix = artifact_prefix(job)
    for local_dir in (clone_dir / "reports", clone_dir / "tests" / "generated"):
        if not local_dir.exists():
            continue
        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(clone_dir).as_posix()
            bucket.blob(f"{prefix}/{relative}").upload_from_filename(str(path))
    return f"https://console.cloud.google.com/storage/browser/{bucket_name}/{prefix}"


def summarize_for_commit_status(result: PipelineResult) -> tuple[str, str]:
    """Return (state, description) for the GitHub commit status."""
    failed = sum(1 for r in result.file_results if r.status in ("failed", "error"))
    passed = sum(1 for r in result.file_results if r.status == "passed")
    skipped = sum(1 for r in result.file_results if r.status == "skipped")
    state = "failure" if failed else "success"
    description = (
        f"generated tests: {passed} passed, {failed} failed, {skipped} skipped"
    )
    return state, description


def post_commit_status(
    job: dict[str, Any], state: str, description: str, target_url: str | None
) -> None:
    """Best-effort: the artifacts are already uploaded, so a GitHub hiccup
    must not fail the job (a retry would be skipped by idempotency and the
    status would never be posted anyway)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    url = (
        f"https://api.github.com/repos/{job['repo_full_name']}"
        f"/statuses/{job['head_sha']}"
    )
    body = {
        "state": state,
        "description": description[:140],
        "context": "ai-test-assistant",
    }
    if target_url:
        body["target_url"] = target_url
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30):
            pass
    except OSError as exc:
        print(
            f"warning: commit status for {artifact_prefix(job)} not posted: {exc}",
            file=sys.stderr,
        )


async def run_analysis_job(job: dict[str, Any]) -> PipelineResult:
    with tempfile.TemporaryDirectory(prefix="ai-test-assistant-") as workdir:
        clone_dir = clone_pr_head(job, Path(workdir))
        result, usage = await run_assistant_on_clone(job, clone_dir)
        record_job_metrics(result, usage)
        artifacts_url = upload_artifacts(job, clone_dir)
        state, description = summarize_for_commit_status(result)
        post_commit_status(job, state, description, artifacts_url)
        return result


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/pubsub")
async def handle_pubsub_push(request: Request) -> Response:
    envelope = await request.json()
    try:
        job = decode_pubsub_push(envelope)
    except MalformedJob as exc:
        # Retrying a malformed message can never succeed; ack it away.
        JOBS_PROCESSED.labels(status="ignored").inc()
        return Response(status_code=200, content=f"ignored: {exc}")

    if report_already_uploaded(job):
        JOBS_PROCESSED.labels(status="skipped").inc()
        return Response(
            status_code=200,
            content=f"skipped: {artifact_prefix(job)} already processed",
        )

    try:
        with JOB_DURATION.time():
            result = await run_analysis_job(job)
    except Exception as exc:  # noqa: BLE001 - let Pub/Sub retry, then dead-letter
        JOBS_PROCESSED.labels(status="failed").inc()
        # Pub/Sub discards the response body, so the reason must be logged
        # here or it is invisible to operators.
        print(
            f"error: job {artifact_prefix(job)} failed: {exc}",
            file=sys.stderr,
        )
        return Response(status_code=500, content=f"processing failed: {exc}")

    JOBS_PROCESSED.labels(status="processed").inc()
    return Response(
        status_code=200,
        content=json.dumps(
            {
                "processed": artifact_prefix(job),
                "files": len(result.file_results),
            }
        ),
        media_type="application/json",
    )
