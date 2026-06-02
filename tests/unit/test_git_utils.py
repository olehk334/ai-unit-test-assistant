"""Tests for git_utils filtering helpers."""

from __future__ import annotations

from pathlib import Path

from ai_test_assistant.git_utils import is_production_python_file


def test_filters_py_files() -> None:
    assert is_production_python_file(Path("examples/a.py"), [])
    assert not is_production_python_file(Path("examples/a.txt"), [])


def test_excludes_test_files() -> None:
    assert not is_production_python_file(Path("tests/test_x.py"), [])
    assert not is_production_python_file(Path("examples/something_test.py"), [])


def test_excludes_generated_files() -> None:
    assert not is_production_python_file(
        Path("examples/foo_generated.py"), []
    )


def test_excludes_paths_from_config() -> None:
    assert not is_production_python_file(
        Path("migrations/0001_init.py"), ["migrations"]
    )
    assert not is_production_python_file(
        Path(".venv/lib/site-packages/x.py"), [".venv"]
    )


def test_includes_normal_source_file() -> None:
    assert is_production_python_file(
        Path("src/pkg/module.py"),
        ["tests/generated", "reports", ".venv", "build", "dist", "migrations"],
    )
