"""Tests for the pytest subprocess runner."""

from __future__ import annotations

from pathlib import Path

from ai_test_assistant.pytest_runner import run_pytest


PASSING_TEST = "def test_ok():\n    assert 1 + 1 == 2\n"
FAILING_TEST = "def test_fail():\n    assert 1 + 1 == 3\n"


def test_returns_passed_result_for_passing_test(tmp_path: Path) -> None:
    test_file = tmp_path / "test_passing.py"
    test_file.write_text(PASSING_TEST, encoding="utf-8")

    result = run_pytest(tmp_path, [test_file])
    assert result.passed is True
    assert result.exit_code == 0
    assert result.duration_seconds >= 0.0


def test_returns_failed_result_for_failing_test(tmp_path: Path) -> None:
    test_file = tmp_path / "test_failing.py"
    test_file.write_text(FAILING_TEST, encoding="utf-8")

    result = run_pytest(tmp_path, [test_file])
    assert result.passed is False
    assert result.exit_code != 0


def test_captures_stdout(tmp_path: Path) -> None:
    test_file = tmp_path / "test_stdout.py"
    test_file.write_text(PASSING_TEST, encoding="utf-8")

    result = run_pytest(tmp_path, [test_file])
    # pytest -q always emits some output (e.g. "1 passed").
    assert result.stdout != ""
