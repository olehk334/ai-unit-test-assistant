"""Generate, update, and repair tests, plus response cleaning + validation."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .llm_client import LlmClient
from .models import SourceAnalysis, TestTarget
from .prompts import (
    build_generate_tests_prompt,
    build_repair_tests_prompt,
    build_update_tests_prompt,
)


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


async def _generate_validated(
    llm: LlmClient, system: str, prompt: str
) -> str:
    raw = await llm.generate(system, prompt)
    cleaned = clean_llm_python_response(raw)
    validate_python_test_code(cleaned)
    return cleaned


async def generate_tests(
    llm: LlmClient,
    analysis: SourceAnalysis,
    targets: list[TestTarget],
    related_tests_content: dict[Path, str],
) -> str:
    """Generate a new pytest test module for the given targets."""
    system, prompt = build_generate_tests_prompt(analysis, targets, related_tests_content)
    return await _generate_validated(llm, system, prompt)


async def update_existing_tests(
    llm: LlmClient,
    analysis: SourceAnalysis,
    targets: list[TestTarget],
    test_file_path: Path,
    existing_test_code: str,
) -> str:
    """Produce an updated version of an existing test file."""
    system, prompt = build_update_tests_prompt(
        analysis, targets, test_file_path, existing_test_code
    )
    return await _generate_validated(llm, system, prompt)


async def repair_tests(
    llm: LlmClient,
    source_code: str,
    test_code: str,
    pytest_output: str,
) -> str:
    """Repair a failing generated test module."""
    system, prompt = build_repair_tests_prompt(source_code, test_code, pytest_output)
    return await _generate_validated(llm, system, prompt)
