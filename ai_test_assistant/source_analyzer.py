"""Parse Python source files and select test targets."""

from __future__ import annotations

import ast
from pathlib import Path

from .models import ClassInfo, FunctionInfo, SourceAnalysis, TestTarget


def _module_path_for(file_path: Path, repo_root: Path) -> str:
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = Path(file_path.name)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts)


def _build_signature(
    name: str, args: ast.arguments, is_async: bool, returns: ast.AST | None
) -> str:
    parts: list[str] = []

    posonly = list(args.posonlyargs)
    regular = list(args.args)
    defaults = list(args.defaults)
    total_with_defaults = posonly + regular
    n_no_default = len(total_with_defaults) - len(defaults)

    for idx, arg in enumerate(total_with_defaults):
        rendered = arg.arg
        if arg.annotation is not None:
            rendered += f": {ast.unparse(arg.annotation)}"
        if idx >= n_no_default:
            default_index = idx - n_no_default
            rendered += f" = {ast.unparse(defaults[default_index])}"
        parts.append(rendered)
        if posonly and idx == len(posonly) - 1:
            parts.append("/")

    if args.vararg is not None:
        rendered = f"*{args.vararg.arg}"
        if args.vararg.annotation is not None:
            rendered += f": {ast.unparse(args.vararg.annotation)}"
        parts.append(rendered)
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        rendered = arg.arg
        if arg.annotation is not None:
            rendered += f": {ast.unparse(arg.annotation)}"
        if default is not None:
            rendered += f" = {ast.unparse(default)}"
        parts.append(rendered)

    if args.kwarg is not None:
        rendered = f"**{args.kwarg.arg}"
        if args.kwarg.annotation is not None:
            rendered += f": {ast.unparse(args.kwarg.annotation)}"
        parts.append(rendered)

    prefix = "async def " if is_async else "def "
    sig = f"{prefix}{name}({', '.join(parts)})"
    if returns is not None:
        sig += f" -> {ast.unparse(returns)}"
    return sig


def _extract_segment(source: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(source, node)
    return segment if segment is not None else ""


def _build_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    source: str,
    qualifier: str | None = None,
) -> FunctionInfo:
    name = node.name
    qualified = f"{qualifier}.{name}" if qualifier else name
    start = node.lineno
    end = node.end_lineno or start
    is_async = isinstance(node, ast.AsyncFunctionDef)
    signature = _build_signature(name, node.args, is_async, node.returns)
    code = _extract_segment(source, node)
    return FunctionInfo(
        name=name,
        qualified_name=qualified,
        start_line=start,
        end_line=end,
        signature=signature,
        source_code=code,
        is_async=is_async,
    )


def analyze_source_file(file_path: Path, repo_root: Path) -> SourceAnalysis:
    """Parse ``file_path`` and return its public functions and classes."""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    functions: list[FunctionInfo] = []
    classes: list[ClassInfo] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            functions.append(_build_function_info(node, source))
        elif isinstance(node, ast.ClassDef):
            if node.name.startswith("_"):
                continue
            methods: list[FunctionInfo] = []
            for body_item in node.body:
                if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if body_item.name.startswith("_"):
                        continue
                    methods.append(
                        _build_function_info(body_item, source, qualifier=node.name)
                    )
            classes.append(
                ClassInfo(
                    name=node.name,
                    start_line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    methods=methods,
                )
            )

    return SourceAnalysis(
        file_path=file_path,
        module_path=_module_path_for(file_path, repo_root),
        source_code=source,
        functions=functions,
        classes=classes,
    )


def _intersects(line_range: tuple[int, int], changed: set[int]) -> bool:
    start, end = line_range
    return any(start <= line <= end for line in changed)


def select_test_targets(
    analysis: SourceAnalysis,
    changed_lines: set[int],
) -> list[TestTarget]:
    """Pick the functions/methods that should receive generated tests."""
    targets: list[TestTarget] = []
    select_all = not changed_lines

    for fn in analysis.functions:
        if select_all or _intersects((fn.start_line, fn.end_line), changed_lines):
            targets.append(
                TestTarget(
                    name=fn.name,
                    qualified_name=fn.qualified_name,
                    target_type="function",
                    source_code=fn.source_code,
                    reason=(
                        "All public functions selected"
                        if select_all
                        else "Function changed in PR"
                    ),
                )
            )

    for cls in analysis.classes:
        for method in cls.methods:
            if select_all or _intersects(
                (method.start_line, method.end_line), changed_lines
            ):
                targets.append(
                    TestTarget(
                        name=method.name,
                        qualified_name=f"{cls.name}.{method.name}",
                        target_type="method",
                        source_code=method.source_code,
                        reason=(
                            "All public methods selected"
                            if select_all
                            else "Method changed in PR"
                        ),
                    )
                )

    return targets
