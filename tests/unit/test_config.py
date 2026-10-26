"""Settings precedence: defaults < ai-test-assistant.yml < environment < CLI flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_test_assistant.config import load_config

ENV_NAMES = (
    "BASE_REF", "OUTPUT_DIR", "SUGGESTIONS_DIR", "REPORT_PATH", "REPAIR_ATTEMPTS",
    "UPDATE_EXISTING_TESTS", "DRY_RUN", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION",
    "GEMINI_MODEL", "TEMPERATURE",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        # setenv first, so the original state comes back even if load_dotenv sets the name.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)


def _write_yaml(repo: Path, text: str) -> None:
    (repo / "ai-test-assistant.yml").write_text(text, encoding="utf-8")


def test_defaults(tmp_path: Path) -> None:
    cfg = load_config(repo_root=tmp_path)

    assert cfg.repo_root == tmp_path.resolve()
    assert cfg.base_ref == "origin/main"
    assert cfg.output_dir == (tmp_path / "tests" / "generated").resolve()
    assert cfg.suggestions_dir == (tmp_path / "reports" / "suggested-tests").resolve()
    assert cfg.report_path == (tmp_path / "reports" / "ai-test-report.md").resolve()
    assert cfg.test_roots == ["tests"]
    assert cfg.exclude_paths == ["tests/generated", "reports", ".venv", "build", "dist", "migrations"]
    assert (cfg.repair_attempts, cfg.update_existing_tests, cfg.dry_run) == (2, True, False)
    assert (cfg.google_cloud_project, cfg.google_cloud_location) == (None, None)
    assert (cfg.gemini_model, cfg.temperature) == ("gemini-2.5-flash", 0.0)


def test_yaml_values_are_coerced_and_override_defaults(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path,
        "base_ref: origin/develop\n"
        "output_dir: out/generated\n"
        "test_roots: [tests, spec]\n"
        "exclude_paths: 'vendor, build'\n"
        "repair_attempts: '3'\n"
        "dry_run: 'yes'\n"
        "update_existing_tests: 'off'\n"
        "temperature: '0.5'\n"
        "source_roots: [src]\n",
    )

    cfg = load_config(repo_root=tmp_path)

    assert cfg.base_ref == "origin/develop"
    assert cfg.output_dir == (tmp_path / "out" / "generated").resolve()
    assert cfg.test_roots == ["tests", "spec"]
    assert cfg.exclude_paths == ["vendor", "build"]
    assert (cfg.repair_attempts, cfg.dry_run, cfg.update_existing_tests) == (3, True, False)
    assert cfg.temperature == 0.5


def test_null_yaml_values_keep_defaults(tmp_path: Path) -> None:
    _write_yaml(tmp_path, "base_ref: null\nrepair_attempts: null\n")

    cfg = load_config(repo_root=tmp_path)

    assert (cfg.base_ref, cfg.repair_attempts) == ("origin/main", 2)


def test_environment_overrides_yaml_and_empty_values_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_yaml(tmp_path, "repair_attempts: 1\ngemini_model: from-yaml\nbase_ref: origin/yaml\n")
    monkeypatch.setenv("REPAIR_ATTEMPTS", "5")
    monkeypatch.setenv("GEMINI_MODEL", "from-env")
    monkeypatch.setenv("BASE_REF", "")

    cfg = load_config(repo_root=tmp_path)

    assert (cfg.repair_attempts, cfg.gemini_model, cfg.base_ref) == (5, "from-env", "origin/yaml")


def test_cli_overrides_environment_and_none_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("REPAIR_ATTEMPTS", "5")

    cfg = load_config(
        repo_root=tmp_path,
        cli_overrides={"dry_run": False, "repair_attempts": None, "report_path": Path("out/report.md")},
    )

    assert (cfg.dry_run, cfg.repair_attempts) == (False, 5)
    assert cfg.report_path == (tmp_path / "out" / "report.md").resolve()


def test_dotenv_fills_unset_variables_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("GEMINI_MODEL=from-dotenv\nREPAIR_ATTEMPTS=9\n", encoding="utf-8")
    monkeypatch.setenv("REPAIR_ATTEMPTS", "4")

    cfg = load_config(repo_root=tmp_path)

    assert (cfg.gemini_model, cfg.repair_attempts) == ("from-dotenv", 4)


def test_explicit_config_file_path(tmp_path: Path) -> None:
    config_file = tmp_path / "custom.yml"
    config_file.write_text("base_ref: origin/custom\n", encoding="utf-8")

    cfg = load_config(repo_root=tmp_path, config_path=config_file)

    assert cfg.base_ref == "origin/custom"
