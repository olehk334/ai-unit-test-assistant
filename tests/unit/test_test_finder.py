"""Tests for test_finder."""

from __future__ import annotations

from pathlib import Path

from ai_test_assistant.models import TestTarget
from ai_test_assistant.test_finder import find_related_tests


def _make_target(name: str) -> TestTarget:
    return TestTarget(
        name=name,
        qualified_name=name,
        target_type="function",
        source_code=f"def {name}(): ...",
        reason="test",
    )


def test_finds_direct_test_file(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "examples").mkdir()
    source = repo / "examples" / "user_service.py"
    source.write_text("def normalize_user_name(name): return name\n", encoding="utf-8")

    (repo / "tests").mkdir()
    direct = repo / "tests" / "test_user_service.py"
    direct.write_text("def test_x(): pass\n", encoding="utf-8")

    found = find_related_tests(source, [_make_target("normalize_user_name")], repo, ["tests"])
    assert direct.resolve() in [p.resolve() for p in found]


def test_finds_test_file_by_import_text(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "examples").mkdir()
    source = repo / "examples" / "user_service.py"
    source.write_text("def normalize_user_name(name): return name\n", encoding="utf-8")

    (repo / "tests").mkdir()
    indirect = repo / "tests" / "test_other.py"
    indirect.write_text(
        "from examples.user_service import normalize_user_name\n"
        "def test_other(): assert normalize_user_name('a') == 'a'\n",
        encoding="utf-8",
    )

    found = find_related_tests(
        source, [_make_target("normalize_user_name")], repo, ["tests"]
    )
    assert indirect.resolve() in [p.resolve() for p in found]


def test_returns_empty_list_when_no_tests(tmp_path: Path) -> None:
    repo = tmp_path
    (repo / "examples").mkdir()
    source = repo / "examples" / "user_service.py"
    source.write_text("def normalize_user_name(name): return name\n", encoding="utf-8")

    # No tests directory exists at all.
    found = find_related_tests(
        source, [_make_target("normalize_user_name")], repo, ["tests"]
    )
    assert found == []
