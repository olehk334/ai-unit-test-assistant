"""Tests for LLM response cleaning and validation."""

from __future__ import annotations

import pytest

from ai_test_assistant.test_generator import (
    ValidationError,
    clean_llm_python_response,
    validate_python_test_code,
)


def test_removes_python_markdown_fences() -> None:
    raw = "```python\ndef test_a():\n    assert True\n```"
    cleaned = clean_llm_python_response(raw)
    assert "```" not in cleaned
    assert "def test_a" in cleaned


def test_removes_bare_fences() -> None:
    raw = "```\ndef test_a():\n    assert True\n```"
    cleaned = clean_llm_python_response(raw)
    assert "```" not in cleaned
    assert cleaned.endswith("\n")


def test_accepts_valid_pytest_code() -> None:
    code = "import pytest\n\n\ndef test_x():\n    assert 1 == 1\n"
    validate_python_test_code(code)


def test_rejects_invalid_python() -> None:
    with pytest.raises(ValidationError):
        validate_python_test_code("def test_x(:\n    assert 1\n")


def test_rejects_empty_response() -> None:
    with pytest.raises(ValidationError):
        validate_python_test_code("")
    with pytest.raises(ValidationError):
        validate_python_test_code("   \n\n")


def test_rejects_code_without_test_function() -> None:
    with pytest.raises(ValidationError):
        validate_python_test_code("def helper():\n    return 1\n")


def test_accepts_test_class() -> None:
    code = "class TestThing:\n    def test_method(self):\n        assert True\n"
    validate_python_test_code(code)
