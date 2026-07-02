"""Prompts must not depend on where the repo was cloned.

The worker clones every job into a fresh temporary directory. If absolute
paths leaked into prompts, identical source code would produce different
prompts per job and the LLM response cache could never hit across jobs.
"""

from __future__ import annotations

from pathlib import Path

from ai_test_assistant.models import SourceAnalysis, TestTarget
from ai_test_assistant.prompts import (
    build_generate_tests_prompt,
    build_update_tests_prompt,
)


def _analysis(clone_dir: str) -> SourceAnalysis:
    return SourceAnalysis(
        file_path=Path(clone_dir) / "pkg" / "module.py",
        module_path="pkg.module",
        source_code="def add(a, b):\n    return a + b\n",
    )


def _target() -> TestTarget:
    return TestTarget(
        name="add",
        qualified_name="add",
        target_type="function",
        source_code="def add(a, b):\n    return a + b",
        reason="Function changed in PR",
    )


def test_generate_prompt_identical_across_clone_locations() -> None:
    related_a = {Path("/tmp/clone-a/tests/test_module.py"): "def test_x(): pass"}
    related_b = {Path("/tmp/clone-b/tests/test_module.py"): "def test_x(): pass"}

    prompt_a = build_generate_tests_prompt(_analysis("/tmp/clone-a"), [_target()], related_a)
    prompt_b = build_generate_tests_prompt(_analysis("/tmp/clone-b"), [_target()], related_b)

    assert prompt_a == prompt_b


def test_update_prompt_identical_across_clone_locations() -> None:
    prompt_a = build_update_tests_prompt(
        _analysis("/tmp/clone-a"),
        [_target()],
        Path("/tmp/clone-a/tests/test_module.py"),
        "def test_x(): pass",
    )
    prompt_b = build_update_tests_prompt(
        _analysis("/tmp/clone-b"),
        [_target()],
        Path("/tmp/clone-b/tests/test_module.py"),
        "def test_x(): pass",
    )

    assert prompt_a == prompt_b
