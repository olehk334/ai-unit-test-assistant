"""One analysis job: clone the PR head, run the assistant, record metrics, upload, report."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from ai_test_assistant.cache import LFUCache, LRUCache
from ai_test_assistant.config import load_config
from ai_test_assistant.llm_client import LlmClient, LlmUsageStats
from ai_test_assistant.models import PipelineResult
from ai_test_assistant.pipeline import run_pr_assistant

from artifact_store import upload_artifacts
from commit_status import post_commit_status, summarize_for_commit_status
from job_message import AnalysisJob
from worker_metrics import record_cache_lookups, record_job_metrics


def _clone_url_with_token(clone_url: str) -> str:
    """Inject GITHUB_TOKEN into GitHub HTTPS URLs so private repos clone."""
    token = os.environ.get("GITHUB_TOKEN")
    if token and clone_url.startswith("https://github.com/"):
        return clone_url.replace("https://", f"https://x-access-token:{token}@", 1)
    return clone_url


def clone_pr_head(job: AnalysisJob, workdir: Path) -> Path:
    clone_dir = workdir / "repo"
    try:
        subprocess.run(
            ["git", "clone", "--quiet", _clone_url_with_token(job.clone_url),
             str(clone_dir)],
            check=True,
            timeout=120,
            capture_output=True,
        )
        # PR refs also cover heads pushed from forks, which a plain clone lacks.
        subprocess.run(
            ["git", "-C", str(clone_dir), "fetch", "--quiet", "origin",
             f"pull/{job.pr_number}/head"],
            check=False,
            timeout=120,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(clone_dir), "checkout", "--quiet", job.head_sha],
            check=True,
            timeout=60,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        # Re-raise without exc.cmd: the clone URL may embed the token.
        raise RuntimeError(
            f"git failed (exit {exc.returncode}) preparing "
            f"{job.repo_full_name}@{job.head_sha}"
        ) from None
    return clone_dir


def run_assistant_on_clone(
    job: AnalysisJob, clone_dir: Path, response_cache: LRUCache | LFUCache
) -> tuple[PipelineResult, LlmUsageStats]:
    config = load_config(
        repo_root=clone_dir,
        cli_overrides={"base_ref": f"origin/{job.base_ref}"},
    )
    llm = LlmClient(config, response_cache=response_cache)
    result = run_pr_assistant(config, llm=llm)
    return result, llm.usage


def run_analysis_job(
    job: AnalysisJob, response_cache: LRUCache | LFUCache
) -> PipelineResult:
    with tempfile.TemporaryDirectory(prefix="ai-test-assistant-") as workdir:
        clone_dir = clone_pr_head(job, Path(workdir))
        # The cache outlives jobs; the metrics need this job's hits and misses only.
        hits_before, misses_before = response_cache.hits, response_cache.misses
        result, usage = run_assistant_on_clone(job, clone_dir, response_cache)
        record_job_metrics(result, usage)
        record_cache_lookups(
            response_cache.policy,
            hits=response_cache.hits - hits_before,
            misses=response_cache.misses - misses_before,
        )
        artifacts_url = upload_artifacts(job, clone_dir)
        state, description = summarize_for_commit_status(result)
        post_commit_status(job, state, description, artifacts_url)
        return result
