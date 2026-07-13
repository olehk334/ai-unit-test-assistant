"""Webhook receiver: turns GitHub PR events into Pub/Sub analysis jobs.

Deliberately does no analysis work itself — it verifies the webhook
signature, filters to the PR events we care about, publishes a job message,
and returns immediately. GitHub webhooks time out after 10 seconds, so the
slow work (clone + LLM + pytest) belongs to the analysis worker behind the
queue.

Environment:
    GITHUB_WEBHOOK_SECRET  shared secret configured on the GitHub webhook
    PUBSUB_TOPIC           full topic path: projects/<project>/topics/<topic>
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import FastAPI, Request, Response

app = FastAPI(title="ai-test-assistant webhook receiver")

_ANALYZABLE_PR_ACTIONS = {"opened", "synchronize", "reopened"}


def verify_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def extract_pr_job(event: dict[str, Any], delivery_id: str) -> dict[str, Any] | None:
    """Return the analysis job for a PR event, or None if it is not analyzable."""
    action = event.get("action")
    pull_request = event.get("pull_request")
    repository = event.get("repository")
    if action not in _ANALYZABLE_PR_ACTIONS or not pull_request or not repository:
        return None
    return {
        "repo_full_name": repository["full_name"],
        "clone_url": repository["clone_url"],
        "pr_number": pull_request["number"],
        "head_sha": pull_request["head"]["sha"],
        "base_ref": pull_request["base"]["ref"],
        "delivery_id": delivery_id,
    }


@functools.lru_cache(maxsize=1)
def _pubsub_publisher():
    # Imported lazily so unit tests do not need the GCP SDK installed
    # (same convention as the lazy google-genai import in llm_client).
    # Cached so every webhook reuses one client connection.
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def publish_pr_job(job: dict[str, Any]) -> str:
    """Publish the job to Pub/Sub and return the message id."""
    topic = os.environ["PUBSUB_TOPIC"]
    future = _pubsub_publisher().publish(topic, json.dumps(job).encode("utf-8"))
    return future.result(timeout=10)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook")
async def receive_webhook(request: Request) -> Response:
    raw_body = await request.body()
    if not verify_webhook_signature(
        raw_body, request.headers.get("X-Hub-Signature-256")
    ):
        return Response(status_code=401, content="invalid signature")

    if request.headers.get("X-GitHub-Event") != "pull_request":
        return Response(status_code=200, content="ignored: not a pull_request event")

    event = json.loads(raw_body)
    job = extract_pr_job(event, request.headers.get("X-GitHub-Delivery", ""))
    if job is None:
        return Response(status_code=200, content="ignored: PR action not analyzable")

    message_id = publish_pr_job(job)
    return Response(
        status_code=202,
        content=json.dumps({"queued": True, "message_id": message_id, "job": job}),
        media_type="application/json",
    )
