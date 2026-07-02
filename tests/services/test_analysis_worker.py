"""Tests for the analysis worker service."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

import worker_app
from ai_test_assistant.models import PipelineResult
from worker_app import MalformedJob, decode_pubsub_push


def _job() -> dict:
    return {
        "repo_full_name": "olehk334/calculator",
        "clone_url": "https://github.com/olehk334/calculator.git",
        "pr_number": 7,
        "head_sha": "abc123",
        "base_ref": "main",
        "delivery_id": "delivery-1",
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
        assert job["repo_full_name"] == "olehk334/calculator"
        assert job["head_sha"] == "abc123"

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
        processed: list[dict] = []

        async def fake_process(job: dict) -> PipelineResult:
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

        async def failing_process(job: dict) -> PipelineResult:
            raise RuntimeError("clone failed")

        monkeypatch.setattr(worker_app, "run_analysis_job", failing_process)

        response = client.post("/pubsub", json=_envelope(_job()))

        assert response.status_code == 500
        assert "processing failed" in response.text

    def test_acks_successful_job(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(worker_app, "report_already_uploaded", lambda job: False)

        async def fake_process(job: dict) -> PipelineResult:
            return PipelineResult()

        monkeypatch.setattr(worker_app, "run_analysis_job", fake_process)

        response = client.post("/pubsub", json=_envelope(_job()))

        assert response.status_code == 200
        assert "processed" in response.text


def test_commit_status_failure_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "token")

    def failing_urlopen(*args, **kwargs):
        raise OSError("github unreachable")

    monkeypatch.setattr(worker_app.urllib.request, "urlopen", failing_urlopen)

    # Must not raise: artifacts are already uploaded, status is best-effort.
    worker_app.post_commit_status(_job(), "success", "all good", None)


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
        state, description = worker_app.summarize_for_commit_status(result)
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
        state, _ = worker_app.summarize_for_commit_status(result)
        assert state == "success"
