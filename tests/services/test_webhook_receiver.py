"""Tests for the webhook receiver service."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

import receiver_app


SECRET = "test-webhook-secret"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(receiver_app.app)


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _pr_event(action: str = "opened") -> dict:
    return {
        "action": action,
        "pull_request": {
            "number": 7,
            "head": {"sha": "abc123"},
            "base": {"ref": "main"},
        },
        "repository": {
            "full_name": "olehk334/calculator",
            "clone_url": "https://github.com/olehk334/calculator.git",
        },
    }


def _post(client: TestClient, event: dict, github_event: str = "pull_request", sign: bool = True):
    body = json.dumps(event).encode()
    headers = {"X-GitHub-Event": github_event}
    if sign:
        headers["X-Hub-Signature-256"] = _sign(body)
    return client.post("/webhook", content=body, headers=headers)


def test_rejects_missing_signature(client: TestClient) -> None:
    response = _post(client, _pr_event(), sign=False)
    assert response.status_code == 401


def test_rejects_wrong_signature(client: TestClient) -> None:
    body = json.dumps(_pr_event()).encode()
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
        },
    )
    assert response.status_code == 401


def test_ignores_non_pr_events(client: TestClient) -> None:
    response = _post(client, {"action": "created"}, github_event="issue_comment")
    assert response.status_code == 200
    assert "ignored" in response.text


def test_ignores_unanalyzable_pr_actions(client: TestClient) -> None:
    response = _post(client, _pr_event(action="closed"))
    assert response.status_code == 200
    assert "ignored" in response.text


def test_publishes_job_for_opened_pr(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    published: list[dict] = []

    def fake_publish(job: dict) -> str:
        published.append(job)
        return "message-42"

    monkeypatch.setattr(receiver_app, "publish_pr_job", fake_publish)

    response = _post(client, _pr_event())

    assert response.status_code == 202
    assert published == [
        {
            "repo_full_name": "olehk334/calculator",
            "clone_url": "https://github.com/olehk334/calculator.git",
            "pr_number": 7,
            "head_sha": "abc123",
            "base_ref": "main",
        }
    ]
