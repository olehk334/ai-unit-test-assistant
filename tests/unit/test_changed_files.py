"""Tests for changed_files filtering helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ai_test_assistant.changed_files import (
    GitError,
    get_changed_python_files,
    is_production_python_file,
)


def test_unknown_base_ref_raises(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=dev@example.com", "-c", "user.name=dev",
         "commit", "-q", "--allow-empty", "-m", "base"],
        cwd=tmp_path,
        check=True,
    )

    with pytest.raises(GitError, match="origin/no-such-branch"):
        get_changed_python_files(tmp_path, "origin/no-such-branch", [])


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
