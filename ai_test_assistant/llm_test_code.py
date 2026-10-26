"""Test code from the LLM: ask, clean the answer, validate it, write it to a file."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .llm_client import LlmClient


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+\-]*\s*\n", re.MULTILINE)
_FENCE_END_RE = re.compile(r"\n```\s*$", re.MULTILINE)

# Obvious shell-prefix indicators that should never appear in a Python test file.
_SHELL_INDICATORS = ("#!/bin/sh", "#!/bin/bash", "#!/usr/bin/env bash")


class ValidationError(ValueError):
    """Raised when LLM output is not valid pytest Python code."""


def clean_llm_python_response(response: str) -> str:
    """Strip Markdown code fences and surrounding whitespace from LLM output."""
    text = response.strip()

    # Remove a leading fence (```python / ```py / ```).
    text = _FENCE_RE.sub("", text, count=1)
    # Remove a trailing fence.
    text = _FENCE_END_RE.sub("", text, count=1)
    # Remove stray prefix backticks left over after the regex above.
    text = text.strip()
    if text.startswith("```"):
        # Fallback: drop the first line if it is still a fence.
        text = text.split("\n", 1)[1] if "\n" in text else ""
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]

    return text.strip() + "\n"


def validate_python_test_code(code: str) -> None:
    """Raise ValidationError if the code is not a valid pytest test module."""
    if not code or not code.strip():
        raise ValidationError("Generated test code is empty")

    lower = code.lower()
    for indicator in _SHELL_INDICATORS:
        if indicator in lower:
            raise ValidationError(
                "Generated code contains a shell shebang and is not valid Python"
            )

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValidationError(f"Generated test code is not valid Python: {exc}") from exc

    has_test = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test_"):
                has_test = True
                break
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            has_test = True
            break

    if not has_test:
        raise ValidationError(
            "Generated code does not contain any pytest test functions or classes"
        )


def ask_for_test_code(llm: LlmClient, system_instruction: str, prompt: str) -> str:
    """Return the LLM's answer as a validated pytest module, or raise ValidationError."""
    code = clean_llm_python_response(llm.generate(system_instruction, prompt))
    validate_python_test_code(code)
    return code


def write_test_code(path: Path, header: str, code: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = code if code.endswith("\n") else code + "\n"
    path.write_text(header + body, encoding="utf-8")
