"""Tests for test_targets."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_test_assistant.test_targets import analyze_source_file, select_test_targets


SAMPLE = '''\
def public_function(a: int, b: int = 1) -> int:
    return a + b


def _private_helper() -> None:
    pass


class Service:
    def public_method(self, value: int) -> int:
        return value * 2

    def _private_method(self) -> None:
        pass


class _PrivateClass:
    def method(self) -> None:
        pass
'''


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def test_detects_public_function(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    names = [fn.name for fn in analysis.functions]
    assert "public_function" in names


def test_ignores_private_function(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    names = [fn.name for fn in analysis.functions]
    assert "_private_helper" not in names


def test_detects_public_methods_of_public_classes(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    qualified = [fn.qualified_name for fn in analysis.functions]
    assert "Service.public_method" in qualified
    assert "Service._private_method" not in qualified
    assert "_PrivateClass.method" not in qualified


def test_select_all_when_no_changed_lines(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    targets = select_test_targets(analysis, set())
    qualified = {t.qualified_name for t in targets}
    assert "public_function" in qualified
    assert "Service.public_method" in qualified


def test_module_functions_come_before_methods(tmp_path: Path) -> None:
    path = tmp_path / "ordered.py"
    path.write_text(
        "class Early:\n    def method(self):\n        return 1\n\n\n"
        "def late_function():\n    return 2\n",
        encoding="utf-8",
    )

    targets = select_test_targets(analyze_source_file(path, tmp_path), set())

    assert [(t.qualified_name, t.target_type, t.reason) for t in targets] == [
        ("late_function", "function", "All public functions selected"),
        ("Early.method", "method", "All public methods selected"),
    ]


def test_select_changed_function_by_line(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    fn = next(fn for fn in analysis.functions if fn.name == "public_function")
    targets = select_test_targets(analysis, {fn.start_line})
    qualified = {t.qualified_name for t in targets}
    assert "public_function" in qualified
    # The method line ranges should not match a function-only change.
    assert "Service.public_method" not in qualified
