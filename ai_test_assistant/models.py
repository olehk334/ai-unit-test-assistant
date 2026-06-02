"""Shared dataclasses used across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChangedFile:
    path: Path
    changed_lines: set[int] = field(default_factory=set)


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str
    start_line: int
    end_line: int
    signature: str
    source_code: str
    is_async: bool = False


@dataclass
class ClassInfo:
    name: str
    start_line: int
    end_line: int
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass
class SourceAnalysis:
    file_path: Path
    module_path: str
    source_code: str
    functions: list[FunctionInfo] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)


@dataclass
class TestTarget:
    name: str
    qualified_name: str
    target_type: str  # "function" or "method"
    source_code: str
    reason: str

    # Tell pytest this is not a test class despite the "Test" prefix.
    __test__ = False


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
    generated_test_file: Path | None = None
    suggested_test_files: list[Path] = field(default_factory=list)
    pytest_result: PytestResult | None = None
    status: str = "pending"
    message: str = ""


@dataclass
class PipelineResult:
    changed_files: list[Path] = field(default_factory=list)
    file_results: list[FileResult] = field(default_factory=list)
