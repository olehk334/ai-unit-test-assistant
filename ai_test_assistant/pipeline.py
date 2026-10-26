"""The assistant's flow: changed files in, generated tests and a report out."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .changed_files import get_changed_python_files
from .config import AppConfig
from .import_graph import order_files_by_imports
from .llm_client import LlmClient
from .models import ChangedFile, FileResult, PipelineResult
from .report import write_json_report, write_markdown_report
from .suggested_updates import suggest_test_updates
from .llm_test_code import ValidationError
from .test_finder import find_related_tests, read_test_files
from .test_generator import generate_and_repair_tests
from .test_targets import analyze_source_file, select_test_targets


def run_pr_assistant(
    config: AppConfig,
    llm: LlmClient | None = None,
) -> PipelineResult:
    """Run the full PR assistant pipeline.

    ``llm`` may be supplied by long-running callers (the analysis worker) so a
    response cache and usage stats survive across pipeline runs.
    """
    llm = llm or LlmClient(config)
    changed_files = get_changed_python_files(
        config.repo_root, config.base_ref, config.exclude_paths
    )
    import_order = order_files_by_imports(changed_files, config.repo_root)

    file_results: list[FileResult] = []
    latest_suggestions: dict[Path, str] = {}
    for changed_file in import_order.ordered_files:
        try:
            file_results.append(write_tests_for_file(config, llm, changed_file, latest_suggestions))
        except Exception as exc:  # noqa: BLE001 - one broken file must not stop the whole PR
            file_results.append(
                FileResult(
                    source_file=changed_file.path,
                    status="error",
                    message=f"Test generation failed: {exc}",
                )
            )

    pipeline_result = PipelineResult(
        changed_files=[cf.path for cf in import_order.ordered_files],
        file_results=file_results,
        import_cycle_files=import_order.cycle_files,
    )
    write_markdown_report(pipeline_result, config.report_path, config.repo_root)
    write_json_report(pipeline_result, config.report_path, config.repo_root)
    return pipeline_result


def run_generate_tests_for_file(config: AppConfig, source: Path) -> FileResult:
    """Generate tests for every public function of one file (``generate-tests``).

    This command never writes suggested updates for existing tests.
    """
    single_file_config = replace(config, update_existing_tests=False)
    return write_tests_for_file(
        single_file_config, LlmClient(config), ChangedFile(path=source), latest_suggestions={}
    )


def write_tests_for_file(
    config: AppConfig,
    llm: LlmClient,
    changed_file: ChangedFile,
    latest_suggestions: dict[Path, str],
) -> FileResult:
    analysis = analyze_source_file(changed_file.path, config.repo_root)
    targets = select_test_targets(analysis, changed_file.changed_lines)
    if not targets:
        return FileResult(
            source_file=changed_file.path,
            status="skipped",
            message="No public functions or methods to test.",
        )

    related_tests = read_test_files(
        find_related_tests(changed_file.path, targets, config.repo_root, config.test_roots)
    )
    try:
        generated_path, pytest_result = generate_and_repair_tests(
            llm, config, analysis, targets, related_tests
        )
    except ValidationError as exc:
        return FileResult(
            source_file=changed_file.path,
            status="error",
            message=f"Generated tests failed validation: {exc}",
        )

    suggested_files: list[Path] = []
    if config.update_existing_tests:
        suggested_files = suggest_test_updates(
            llm, config, analysis, targets, related_tests, latest_suggestions
        )

    passed = pytest_result.passed
    return FileResult(
        source_file=changed_file.path,
        generated_test_file=generated_path,
        suggested_test_files=suggested_files,
        pytest_result=pytest_result,
        status="passed" if passed else "failed",
        message="Generated tests passed." if passed else "Generated tests failed even after repair attempts.",
    )
