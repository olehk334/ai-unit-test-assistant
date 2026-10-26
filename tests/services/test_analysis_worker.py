"""Tests for the analysis worker service."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

import analysis_job
import commit_status
import worker_app
from ai_test_assistant.cache import LFUCache, LRUCache
from ai_test_assistant.models import PipelineResult
from job_message import AnalysisJob, MalformedJob, decode_pubsub_push


def _job() -> dict:
    return {
        "repo_full_name": "olehk334/calculator",
        "clone_url": "https://github.com/olehk334/calculator.git",
        "pr_number": 7,
        "head_sha": "abc123",
        "base_ref": "main",
    }


def _envelope(job: dict) -> dict:
    data = base64.b64encode(json.dumps(job).encode()).decode()
    return {"message": {"data": data, "messageId": "1"}, "subscription": "s"}


@pytest.fixture()
def client() -> TestClient:
    return TestClient(worker_app.app)


class TestDecodePubsubPush:
    def test_decodes_valid_envelope(self) -> None:
        job = decode_pubsub_push(_envelope(_job()))
        assert job == AnalysisJob(**_job())
        assert job.artifact_prefix == "olehk334/calculator/7/abc123"

    def test_ignores_fields_it_does_not_know(self) -> None:
        # Messages queued by an older receiver still carry delivery_id.
        job = decode_pubsub_push(_envelope({**_job(), "delivery_id": "d-1"}))
        assert job == AnalysisJob(**_job())

    def test_rejects_missing_message(self) -> None:
        with pytest.raises(MalformedJob):
            decode_pubsub_push({"subscription": "s"})

    def test_rejects_bad_base64(self) -> None:
        with pytest.raises(MalformedJob):
            decode_pubsub_push({"message": {"data": "not-base64!!!"}})

    def test_rejects_job_with_missing_fields(self) -> None:
        incomplete = {"repo_full_name": "x/y"}
        with pytest.raises(MalformedJob):
            decode_pubsub_push(_envelope(incomplete))


class TestPubsubEndpoint:
    def test_acks_malformed_message_without_retry(self, client: TestClient) -> None:
        response = client.post("/pubsub", json={"message": {"data": "%%%"}})
        assert response.status_code == 200
        assert "ignored" in response.text

    def test_skips_already_processed_job(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_app, "report_already_uploaded", lambda job: True)
        processed: list[AnalysisJob] = []

        def fake_process(job: AnalysisJob, response_cache: LRUCache) -> PipelineResult:
            processed.append(job)
            return PipelineResult()

        monkeypatch.setattr(worker_app, "run_analysis_job", fake_process)

        response = client.post("/pubsub", json=_envelope(_job()))

        assert response.status_code == 200
        assert "skipped" in response.text
        assert processed == []

    def test_returns_500_so_pubsub_retries_on_failure(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_app, "report_already_uploaded", lambda job: False)

        def failing_process(job: AnalysisJob, response_cache: LRUCache) -> PipelineResult:
            raise RuntimeError("clone failed")

        monkeypatch.setattr(worker_app, "run_analysis_job", failing_process)

        response = client.post("/pubsub", json=_envelope(_job()))

        assert response.status_code == 500
        assert "processing failed" in response.text

    def test_acks_successful_job(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_app, "report_already_uploaded", lambda job: False)

        def fake_process(job: AnalysisJob, response_cache: LRUCache) -> PipelineResult:
            return PipelineResult()

        monkeypatch.setattr(worker_app, "run_analysis_job", fake_process)

        response = client.post("/pubsub", json=_envelope(_job()))

        assert response.status_code == 200
        assert "processed" in response.text


class TestResponseCacheFromEnv:
    def test_lru_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_CACHE_POLICY", raising=False)
        assert isinstance(worker_app.response_cache_from_env(), LRUCache)

    def test_lfu_on_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_CACHE_POLICY", "LFU")
        assert isinstance(worker_app.response_cache_from_env(), LFUCache)

    def test_rejects_unknown_policy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_CACHE_POLICY", "fifo")
        with pytest.raises(ValueError, match="LLM_CACHE_POLICY"):
            worker_app.response_cache_from_env()


class TestCloneUrlWithToken:
    def test_injects_token_for_github_https(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "tok123")
        url = analysis_job._clone_url_with_token("https://github.com/o/r.git")
        assert url == "https://x-access-token:tok123@github.com/o/r.git"

    def test_unchanged_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        url = analysis_job._clone_url_with_token("https://github.com/o/r.git")
        assert url == "https://github.com/o/r.git"

    def test_unchanged_for_non_github_urls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "tok123")
        assert analysis_job._clone_url_with_token("/repos/calculator") == "/repos/calculator"


def test_commit_status_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def failing_urlopen(*args, **kwargs):
        raise OSError("github unreachable")

    monkeypatch.setattr(commit_status.urllib.request, "urlopen", failing_urlopen)

    # Must not raise: artifacts are already uploaded, status is best-effort.
    commit_status.post_commit_status(AnalysisJob(**_job()), "success", "all good", None)


def test_health_answers_while_a_job_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    job_started = threading.Event()
    job_finished_at: list[float] = []

    def slow_clone(job, workdir):
        job_started.set()
        time.sleep(1.0)
        job_finished_at.append(time.monotonic())
        raise RuntimeError("clone stub")

    monkeypatch.setattr(analysis_job, "clone_pr_head", slow_clone)

    async def health_answer_time() -> float:
        transport = httpx.ASGITransport(app=worker_app.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
            job_request = asyncio.create_task(client.post("/pubsub", json=_envelope(_job())))
            await asyncio.to_thread(job_started.wait, 5)
            await client.get("/health")
            answered_at = time.monotonic()
            await job_request
            return answered_at

    answered_at = asyncio.run(health_answer_time())

    assert answered_at < job_finished_at[0]


def test_job_outcomes_are_exported_at_zero_from_startup() -> None:
    # A fresh process, so no earlier test has created these series already.
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    env.pop("LLM_CACHE_POLICY", None)
    exposition = subprocess.run(
        [sys.executable, "-c",
         "import worker_app, prometheus_client; print(prometheus_client.generate_latest().decode())"],
        capture_output=True, text=True, check=True, env=env,
    ).stdout

    for series in (
        'jobs_processed_total{status="processed"} 0.0',
        'jobs_processed_total{status="failed"} 0.0',
        'generated_test_files_total{result="failed"} 0.0',
        'llm_cache_hits_total{policy="lru"} 0.0',
    ):
        assert series in exposition


def test_metrics_endpoint_exposes_job_counters(client: TestClient) -> None:
    # A malformed message still counts as a job outcome.
    client.post("/pubsub", json={"message": {"data": "%%%"}})

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "jobs_processed_total" in response.text


class TestCommitStatusSummary:
    def test_failure_when_any_file_failed(self) -> None:
        from pathlib import Path

        from ai_test_assistant.models import FileResult

        result = PipelineResult(
            file_results=[
                FileResult(source_file=Path("a.py"), status="passed"),
                FileResult(source_file=Path("b.py"), status="failed"),
            ]
        )
        state, description = commit_status.summarize_for_commit_status(result)
        assert state == "failure"
        assert "1 failed" in description

    def test_success_when_all_passed_or_skipped(self) -> None:
        from pathlib import Path

        from ai_test_assistant.models import FileResult

        result = PipelineResult(
            file_results=[
                FileResult(source_file=Path("a.py"), status="passed"),
                FileResult(source_file=Path("b.py"), status="skipped"),
            ]
        )
        state, _ = commit_status.summarize_for_commit_status(result)
        assert state == "success"


def _repo_with_one_changed_function(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "origin"
    repo.mkdir()

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "dev@example.com")
    git("config", "user.name", "dev")
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "base")
    git("checkout", "-q", "-b", "feature")
    (repo / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    git("commit", "-q", "-am", "feature")
    return repo, git("rev-parse", "HEAD")


@pytest.mark.parametrize("cache_class", [LRUCache, LFUCache])
def test_second_run_of_a_job_is_served_from_the_response_cache(
    cache_class: type[LRUCache] | type[LFUCache],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    repo, head_sha = _repo_with_one_changed_function(tmp_path)
    job = AnalysisJob(
        repo_full_name="local/calc",
        clone_url=str(repo),
        pr_number=1,
        head_sha=head_sha,
        base_ref="main",
    )
    cache = cache_class(capacity=8)
    labels = {"policy": cache.policy}

    def cache_lookups() -> tuple[float, float]:
        return (
            REGISTRY.get_sample_value("llm_cache_hits_total", labels) or 0.0,
            REGISTRY.get_sample_value("llm_cache_misses_total", labels) or 0.0,
        )

    start = cache_lookups()
    first = analysis_job.run_analysis_job(job, cache)
    after_first = cache_lookups()
    analysis_job.run_analysis_job(job, cache)
    after_second = cache_lookups()

    assert [r.status for r in first.file_results] == ["passed"]
    assert (after_first[0] - start[0], after_first[1] - start[1]) == (0, 1)
    assert (after_second[0] - after_first[0], after_second[1] - after_first[1]) == (1, 0)
