"""Shared dataclasses used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChangedFile:
    path: Path
    changed_lines: set[int] = field(default_factory=set)


@dataclass
class TestTarget:
    """A public function or method; ``reason`` says why it was selected for tests."""

    name: str
    qualified_name: str
    target_type: str  # "function" or "method"
    start_line: int
    end_line: int
    source_code: str
    reason: str = ""

    # Tell pytest this is not a test class despite the "Test" prefix.
    __test__ = False


@dataclass
class SourceAnalysis:
    file_path: Path
    module_path: str
    source_code: str
    functions: list[TestTarget] = field(default_factory=list)


@dataclass
class PytestResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float


@dataclass
class FileResult:
    source_file: Path
    status: str  # "passed", "failed", "skipped" or "error"
    message: str = ""
    generated_test_file: Path | None = None
    suggested_test_files: list[Path] = field(default_factory=list)
    pytest_result: PytestResult | None = None


@dataclass
class PipelineResult:
    changed_files: list[Path] = field(default_factory=list)
    file_results: list[FileResult] = field(default_factory=list)
    # Files whose imports form a cycle; they were processed in original order.
    import_cycle_files: list[Path] = field(default_factory=list)
