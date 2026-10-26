"""The job message the webhook receiver publishes and the worker consumes."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass, fields
from typing import Any


class MalformedJob(ValueError):
    """Message cannot ever be processed; ack it instead of retrying forever."""


@dataclass(frozen=True)
class AnalysisJob:
    repo_full_name: str
    clone_url: str
    pr_number: int
    head_sha: str
    base_ref: str

    @property
    def artifact_prefix(self) -> str:
        return f"{self.repo_full_name}/{self.pr_number}/{self.head_sha}"


_JOB_FIELDS = tuple(field.name for field in fields(AnalysisJob))


def decode_pubsub_push(envelope: dict[str, Any]) -> AnalysisJob:
    message = envelope.get("message")
    if not isinstance(message, dict) or "data" not in message:
        raise MalformedJob("missing message.data in Pub/Sub envelope")
    try:
        payload = base64.b64decode(message["data"])
        job = json.loads(payload)
    except (binascii.Error, ValueError) as exc:
        raise MalformedJob(f"undecodable job payload: {exc}") from exc

    missing = set(_JOB_FIELDS) - job.keys()
    if missing:
        raise MalformedJob(f"job missing fields: {sorted(missing)}")
    return AnalysisJob(**{name: job[name] for name in _JOB_FIELDS})
