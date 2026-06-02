"""Tests for source_analyzer."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_test_assistant.source_analyzer import analyze_source_file, select_test_targets


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


def test_detects_class_method(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    classes = {cls.name: cls for cls in analysis.classes}
    assert "Service" in classes
    method_names = [m.name for m in classes["Service"].methods]
    assert "public_method" in method_names
    assert "_private_method" not in method_names
    assert "_PrivateClass" not in classes


def test_select_all_when_no_changed_lines(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    targets = select_test_targets(analysis, set())
    qualified = {t.qualified_name for t in targets}
    assert "public_function" in qualified
    assert "Service.public_method" in qualified


def test_select_changed_function_by_line(sample_file: Path, tmp_path: Path) -> None:
    analysis = analyze_source_file(sample_file, tmp_path)
    fn = next(fn for fn in analysis.functions if fn.name == "public_function")
    targets = select_test_targets(analysis, {fn.start_line})
    qualified = {t.qualified_name for t in targets}
    assert "public_function" in qualified
    # The method line ranges should not match a function-only change.
    assert "Service.public_method" not in qualified
