"""The GitHub commit status that shows the result on the pull request."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

from ai_test_assistant.models import PipelineResult

from job_message import AnalysisJob


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
    job: AnalysisJob, state: str, description: str, target_url: str | None
) -> None:
    """Best-effort: the artifacts are already uploaded, so a GitHub hiccup
    must not fail the job (a retry would be skipped by idempotency and the
    status would never be posted anyway)."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        return
    url = (
        f"https://api.github.com/repos/{job.repo_full_name}"
        f"/statuses/{job.head_sha}"
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
            f"warning: commit status for {job.artifact_prefix} not posted: {exc}",
            file=sys.stderr,
        )
