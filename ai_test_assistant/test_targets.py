"""Parse Python source files and select test targets."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

from .models import SourceAnalysis, TestTarget
from .repo_paths import module_name


_SELECTION_REASONS = {
    ("function", True): "All public functions selected",
    ("function", False): "Function changed in PR",
    ("method", True): "All public methods selected",
    ("method", False): "Method changed in PR",
}


def _is_public_function(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")


def _target(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    class_name: str | None = None,
) -> TestTarget:
    return TestTarget(
        name=node.name,
        qualified_name=f"{class_name}.{node.name}" if class_name else node.name,
        target_type="method" if class_name else "function",
        start_line=node.lineno,
        end_line=node.end_lineno or node.lineno,
        source_code=ast.get_source_segment(source, node) or "",
    )


def analyze_source_file(file_path: Path, repo_root: Path) -> SourceAnalysis:
    """Parse ``file_path`` and return its public functions and methods."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions = [_target(node, source) for node in tree.body if _is_public_function(node)]
    # Methods follow all module-level functions: target order is part of the prompt text.
    methods = [
        _target(item, source, class_name=node.name)
        for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
        for item in node.body
        if _is_public_function(item)
    ]

    return SourceAnalysis(
        file_path=file_path,
        module_path=module_name(file_path, repo_root),
        source_code=source,
        functions=functions + methods,
    )


def _intersects(target: TestTarget, changed: set[int]) -> bool:
    return any(target.start_line <= line <= target.end_line for line in changed)


def select_test_targets(
    analysis: SourceAnalysis,
    changed_lines: set[int],
) -> list[TestTarget]:
    """Pick the functions/methods that should receive generated tests."""
    select_all = not changed_lines
    return [
        replace(target, reason=_SELECTION_REASONS[(target.target_type, select_all)])
        for target in analysis.functions
        if select_all or _intersects(target, changed_lines)
    ]
