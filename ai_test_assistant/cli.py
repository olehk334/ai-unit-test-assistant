"""Typer-based CLI for the AI Unit Test Assistant."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

import typer

from .config import AppConfig, load_config
from .pipeline import (
    apply_suggested_updates,
    run_generate_tests_for_file,
    run_pr_assistant,
)


app = typer.Typer(
    name="ai-test-assistant",
    help="AI-powered pytest unit test generator using Gemini through Vertex AI.",
    add_completion=False,
    no_args_is_help=True,
)


def _build_config(
    base_ref: Optional[str],
    output_dir: Optional[Path],
    suggestions_dir: Optional[Path],
    report: Optional[Path],
    repair_attempts: Optional[int],
    dry_run: Optional[bool],
    update_existing_tests: Optional[bool],
    config_file: Optional[Path],
) -> AppConfig:
    overrides: dict[str, object] = {}
    if base_ref is not None:
        overrides["base_ref"] = base_ref
    if output_dir is not None:
        overrides["output_dir"] = output_dir
    if suggestions_dir is not None:
        overrides["suggestions_dir"] = suggestions_dir
    if report is not None:
        overrides["report_path"] = report
    if repair_attempts is not None:
        overrides["repair_attempts"] = repair_attempts
    if dry_run is not None:
        overrides["dry_run"] = dry_run
    if update_existing_tests is not None:
        overrides["update_existing_tests"] = update_existing_tests

    return load_config(config_path=config_file, cli_overrides=overrides)


@app.command("generate-tests")
def generate_tests_command(
    source: Path = typer.Option(..., "--source", help="Source Python file."),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Directory for generated test files."
    ),
    repair_attempts: Optional[int] = typer.Option(
        None, "--repair-attempts", help="Number of repair attempts."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Skip LLM calls and use a placeholder response."
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", help="Path to ai-test-assistant.yml."
    ),
) -> None:
    """Generate pytest tests for a single source file."""
    cfg = _build_config(
        base_ref=None,
        output_dir=output_dir,
        suggestions_dir=None,
        report=None,
        repair_attempts=repair_attempts,
        dry_run=dry_run if dry_run else None,
        update_existing_tests=None,
        config_file=config_file,
    )
    result = asyncio.run(run_generate_tests_for_file(cfg, source.resolve()))
    typer.echo(f"Status: {result.status}")
    if result.generated_test_file:
        typer.echo(f"Generated: {result.generated_test_file}")
    if result.pytest_result is not None:
        typer.echo(
            f"pytest passed={result.pytest_result.passed} "
            f"exit_code={result.pytest_result.exit_code}"
        )
    if result.message:
        typer.echo(result.message)


@app.command("run-pr-assistant")
def run_pr_assistant_command(
    base_ref: Optional[str] = typer.Option(
        None, "--base-ref", help="Git base ref (e.g. origin/main)."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", help="Directory for generated test files."
    ),
    suggestions_dir: Optional[Path] = typer.Option(
        None, "--suggestions-dir", help="Directory for suggested test updates."
    ),
    report: Optional[Path] = typer.Option(
        None, "--report", help="Path to the markdown report file."
    ),
    repair_attempts: Optional[int] = typer.Option(
        None, "--repair-attempts", help="Number of repair attempts."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Skip LLM calls and use a placeholder response."
    ),
    update_existing_tests: Optional[bool] = typer.Option(
        None,
        "--update-existing-tests/--no-update-existing-tests",
        help="Suggest updates for existing related tests.",
    ),
    config_file: Optional[Path] = typer.Option(
        None, "--config", help="Path to ai-test-assistant.yml."
    ),
) -> None:
    """Detect changed files and generate/suggest tests for them."""
    cfg = _build_config(
        base_ref=base_ref,
        output_dir=output_dir,
        suggestions_dir=suggestions_dir,
        report=report,
        repair_attempts=repair_attempts,
        dry_run=dry_run if dry_run else None,
        update_existing_tests=update_existing_tests,
        config_file=config_file,
    )

    result = asyncio.run(run_pr_assistant(cfg))
    typer.echo(
        f"Changed files: {len(result.changed_files)}  "
        f"Processed: {len(result.file_results)}"
    )
    typer.echo(f"Report: {cfg.report_path}")


@app.command("apply-suggestions")
def apply_suggestions_command(
    suggestions_dir: Path = typer.Option(
        Path("reports/suggested-tests"),
        "--suggestions-dir",
        help="Directory containing the suggested test updates.",
    ),
    repo_root: Optional[Path] = typer.Option(
        None, "--repo-root", help="Repo root to apply suggestions into."
    ),
    strip_header: bool = typer.Option(
        True,
        "--strip-header/--keep-header",
        help="Strip the AI-generated suggestion header before writing.",
    ),
) -> None:
    """Copy suggested test updates over the original test files.

    Each file under ``--suggestions-dir`` is written to the same relative path
    under ``--repo-root`` (defaults to the current working directory),
    overwriting any existing file.
    """
    root = (repo_root or Path.cwd()).resolve()
    src_dir = (
        suggestions_dir.resolve()
        if suggestions_dir.is_absolute()
        else (root / suggestions_dir).resolve()
    )

    if not src_dir.exists():
        typer.echo(f"No suggestions directory at {src_dir}.")
        return

    applied = apply_suggested_updates(src_dir, root, strip_header=strip_header)
    if not applied:
        typer.echo("No suggested files to apply.")
        return

    for dest in applied:
        try:
            rel = dest.relative_to(root)
        except ValueError:
            rel = dest
        typer.echo(f"Applied: {rel}")
    typer.echo(f"\nApplied {len(applied)} file(s).")


if __name__ == "__main__":  # pragma: no cover - manual invocation
    app()
