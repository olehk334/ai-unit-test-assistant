"""Markdown and JSON report writers."""

from __future__ import annotations

import json
from pathlib import Path

from .models import FileResult, PipelineResult


def _relative_or_str(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _summarize(result: PipelineResult) -> dict[str, int]:
    files_with_generated = sum(
        1 for r in result.file_results if r.generated_test_file is not None
    )
    files_with_suggestions = sum(
        1 for r in result.file_results if r.suggested_test_files
    )
    passed = sum(
        1
        for r in result.file_results
        if r.pytest_result is not None and r.pytest_result.passed
    )
    failed = sum(
        1
        for r in result.file_results
        if r.pytest_result is not None and not r.pytest_result.passed
    )
    return {
        "changed_files": len(result.changed_files),
        "files_with_generated_tests": files_with_generated,
        "files_with_suggested_updates": files_with_suggestions,
        "passed_generated_tests": passed,
        "failed_generated_tests": failed,
    }


def _format_file_result(file_result: FileResult, root: Path) -> list[str]:
    lines: list[str] = []
    source_rel = _relative_or_str(file_result.source_file, root)
    lines.append(f"### {source_rel}")
    lines.append("")
    lines.append(f"Status: {file_result.status.upper()}")

    generated_rel = _relative_or_str(file_result.generated_test_file, root)
    if generated_rel:
        lines.append(f"Generated test file: {generated_rel}")

    if file_result.suggested_test_files:
        lines.append("Suggested updates:")
        for path in file_result.suggested_test_files:
            lines.append(f"- {_relative_or_str(path, root)}")

    if file_result.pytest_result is not None:
        pr = file_result.pytest_result
        lines.append(
            f"pytest: passed={pr.passed} exit_code={pr.exit_code} "
            f"duration={pr.duration_seconds:.2f}s"
        )

    if file_result.message:
        lines.append("")
        lines.append("Message:")
        lines.append(file_result.message.strip())

    lines.append("")
    return lines


def write_markdown_report(result: PipelineResult, report_path: Path, repo_root: Path) -> None:
    """Write a human-readable Markdown report."""
    summary = _summarize(result)
    lines: list[str] = []
    lines.append("# AI Unit Test Assistant Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"Changed production files: {summary['changed_files']}")
    lines.append(f"Files with generated tests: {summary['files_with_generated_tests']}")
    lines.append(
        f"Files with suggested test updates: {summary['files_with_suggested_updates']}"
    )
    lines.append(f"Passed generated tests: {summary['passed_generated_tests']}")
    lines.append(f"Failed generated tests: {summary['failed_generated_tests']}")
    lines.append("")
    lines.append("## Details")
    lines.append("")

    if not result.file_results:
        lines.append("_No changed production Python files were detected._")
        lines.append("")
    else:
        for file_result in result.file_results:
            lines.extend(_format_file_result(file_result, repo_root))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_json_report(result: PipelineResult, report_path: Path, repo_root: Path) -> None:
    """Write a machine-readable JSON report next to the Markdown report."""
    summary = _summarize(result)
    payload = {
        "summary": summary,
        "changed_files": [_relative_or_str(p, repo_root) for p in result.changed_files],
        "files": [
            {
                "source_file": _relative_or_str(r.source_file, repo_root),
                "status": r.status,
                "message": r.message,
                "generated_test_file": _relative_or_str(r.generated_test_file, repo_root),
                "suggested_test_files": [
                    _relative_or_str(p, repo_root) for p in r.suggested_test_files
                ],
                "pytest": (
                    None
                    if r.pytest_result is None
                    else {
                        "passed": r.pytest_result.passed,
                        "exit_code": r.pytest_result.exit_code,
                        "duration_seconds": r.pytest_result.duration_seconds,
                    }
                ),
            }
            for r in result.file_results
        ],
    }
    json_path = report_path.with_suffix(".json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
