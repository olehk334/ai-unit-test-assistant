"""Invalid input must fail with a clear message, never succeed silently."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ai_test_assistant.cli import app


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=dev@example.com", "-c", "user.name=dev",
         "commit", "-q", "-m", "base"],
        cwd=tmp_path,
        check=True,
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_unknown_base_ref_fails_instead_of_reporting_no_changes(repo: Path) -> None:
    result = CliRunner().invoke(
        app, ["run-pr-assistant", "--base-ref", "origin/no-such-branch", "--dry-run"]
    )

    assert result.exit_code == 1
    assert "origin/no-such-branch" in result.output
    assert not (repo / "reports").exists()


def test_missing_source_file_is_reported_without_a_traceback(repo: Path) -> None:
    result = CliRunner().invoke(app, ["generate-tests", "--source", "missing.py", "--dry-run"])

    assert result.exit_code == 2
    assert "does not exist" in result.output
