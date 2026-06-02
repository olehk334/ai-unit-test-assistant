"""Prompt templates for the LLM."""

from __future__ import annotations

from pathlib import Path

from .models import SourceAnalysis, TestTarget


GENERATE_SYSTEM_INSTRUCTION = """You are a senior Python engineer specializing in pytest unit tests.

Generate unit tests for the provided Python source code.

Rules:
- Return only valid Python code.
- Do not include Markdown fences.
- Do not include explanations.
- Do not modify production code.
- Use pytest.
- Prefer deterministic tests.
- Cover normal cases, edge cases, and error cases.
- Mock external dependencies only when necessary.
- Do not over-mock pure functions.
- Do not test private implementation details.
- Use clear test names.
"""


REPAIR_SYSTEM_INSTRUCTION = """You are a senior Python engineer fixing generated pytest tests.

The generated test file failed.

Rules:
- Fix only the test code.
- Do not modify production code.
- Return only valid Python code.
- Do not include Markdown fences.
- Preserve useful tests.
- Remove invalid assumptions.
- Fix imports, fixtures, mocks, and expected values.
"""


UPDATE_SYSTEM_INSTRUCTION = """You are a senior Python engineer updating existing pytest tests after production code changes.

Rules:
- Return the full updated test file.
- Do not return a diff.
- Do not include Markdown fences.
- Do not include explanations.
- Do not modify production code.
- Preserve existing valuable tests.
- Update tests that no longer match public behavior.
- Add tests for new public behavior when useful.
- Keep the existing style of the test file.
"""


def _format_targets(targets: list[TestTarget]) -> str:
    lines: list[str] = []
    for idx, target in enumerate(targets, 1):
        lines.append(
            f"--- Target {idx}: {target.qualified_name} ({target.target_type}) ---"
        )
        lines.append(f"Reason: {target.reason}")
        lines.append(target.source_code.strip())
        lines.append("")
    return "\n".join(lines).strip()


def _format_related_tests(related: dict[Path, str]) -> str:
    if not related:
        return "(no related test files were found)"
    chunks: list[str] = []
    for path, content in related.items():
        chunks.append(f"--- Existing test file: {path} ---")
        chunks.append(content.strip())
        chunks.append("")
    return "\n".join(chunks).strip()


def build_generate_tests_prompt(
    analysis: SourceAnalysis,
    targets: list[TestTarget],
    related_tests_content: dict[Path, str],
) -> tuple[str, str]:
    """Build the (system_instruction, user_prompt) pair for new test generation."""
    user_prompt = (
        f"Module path: {analysis.module_path}\n"
        f"Source file: {analysis.file_path}\n\n"
        f"Full source code:\n"
        f"```\n{analysis.source_code.strip()}\n```\n\n"
        f"Test targets to cover:\n{_format_targets(targets)}\n\n"
        f"Existing related tests for reference (do not duplicate them):\n"
        f"{_format_related_tests(related_tests_content)}\n\n"
        f"Write a single self-contained pytest test module that imports from "
        f"`{analysis.module_path}` and exercises the targets above. Return Python code only."
    )
    return GENERATE_SYSTEM_INSTRUCTION, user_prompt


def build_repair_tests_prompt(
    source_code: str,
    test_code: str,
    pytest_output: str,
) -> tuple[str, str]:
    """Build the (system_instruction, user_prompt) pair for repairing tests."""
    user_prompt = (
        "Production source code (DO NOT MODIFY):\n"
        f"```\n{source_code.strip()}\n```\n\n"
        "Current generated test file (FIX THIS):\n"
        f"```\n{test_code.strip()}\n```\n\n"
        "pytest output (use this to diagnose the failure):\n"
        f"```\n{pytest_output.strip()}\n```\n\n"
        "Return the corrected full test file as Python code only."
    )
    return REPAIR_SYSTEM_INSTRUCTION, user_prompt


def build_update_tests_prompt(
    analysis: SourceAnalysis,
    targets: list[TestTarget],
    test_file_path: Path,
    existing_test_code: str,
) -> tuple[str, str]:
    """Build the (system_instruction, user_prompt) pair for updating existing tests."""
    user_prompt = (
        f"Production module: {analysis.module_path}\n"
        f"Production source file: {analysis.file_path}\n\n"
        f"Current production source code:\n"
        f"```\n{analysis.source_code.strip()}\n```\n\n"
        f"Changed/affected targets:\n{_format_targets(targets)}\n\n"
        f"Existing test file path: {test_file_path}\n"
        f"Existing test file content:\n"
        f"```\n{existing_test_code.strip()}\n```\n\n"
        "Produce the full updated test file. Return Python code only."
    )
    return UPDATE_SYSTEM_INSTRUCTION, user_prompt
