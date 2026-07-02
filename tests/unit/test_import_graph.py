"""Tests for import-dependency ordering of changed files."""

from __future__ import annotations

from pathlib import Path

from ai_test_assistant.import_graph import order_files_by_imports
from ai_test_assistant.models import ChangedFile


def _write(repo: Path, rel: str, source: str) -> ChangedFile:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return ChangedFile(path=path)


def _names(order) -> list[str]:
    return [cf.path.name for cf in order.ordered_files]


def test_dependency_comes_before_dependent(tmp_path: Path) -> None:
    service = _write(tmp_path, "service.py", "from models import User\n")
    models = _write(tmp_path, "models.py", "class User: ...\n")

    order = order_files_by_imports([service, models], tmp_path)

    assert _names(order) == ["models.py", "service.py"]
    assert order.cycle_files == []


def test_diamond_dependencies_resolve(tmp_path: Path) -> None:
    base = _write(tmp_path, "base.py", "X = 1\n")
    left = _write(tmp_path, "left.py", "import base\n")
    right = _write(tmp_path, "right.py", "import base\n")
    top = _write(tmp_path, "top.py", "import left\nimport right\n")

    order = order_files_by_imports([top, left, right, base], tmp_path)
    names = _names(order)

    assert names[0] == "base.py"
    assert names[-1] == "top.py"


def test_cycle_reported_and_original_order_kept(tmp_path: Path) -> None:
    a = _write(tmp_path, "a.py", "import b\n")
    b = _write(tmp_path, "b.py", "import a\n")

    order = order_files_by_imports([a, b], tmp_path)

    assert _names(order) == ["a.py", "b.py"]
    assert sorted(p.name for p in order.cycle_files) == ["a.py", "b.py"]


def test_unrelated_files_keep_original_order(tmp_path: Path) -> None:
    first = _write(tmp_path, "first.py", "import os\n")
    second = _write(tmp_path, "second.py", "import sys\n")

    order = order_files_by_imports([first, second], tmp_path)

    assert _names(order) == ["first.py", "second.py"]
    assert order.cycle_files == []


def test_relative_import_inside_package(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    pricing = _write(tmp_path, "pkg/pricing.py", "from .operations import add\n")
    operations = _write(tmp_path, "pkg/operations.py", "def add(a, b): return a + b\n")

    order = order_files_by_imports([pricing, operations], tmp_path)

    assert _names(order) == ["operations.py", "pricing.py"]


def test_single_file_passes_through(tmp_path: Path) -> None:
    only = _write(tmp_path, "only.py", "import os\n")

    order = order_files_by_imports([only], tmp_path)

    assert _names(order) == ["only.py"]
