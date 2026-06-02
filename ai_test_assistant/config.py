"""Application configuration loading.

Priority (highest first):
    CLI args > environment variables > config file > defaults
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:  # Optional .env autoloading.
    from dotenv import load_dotenv as _load_dotenv
except ImportError:  # pragma: no cover - dotenv is an installed dep, but keep it optional.
    _load_dotenv = None  # type: ignore[assignment]


DEFAULT_CONFIG_FILENAME = "ai-test-assistant.yml"
DEFAULT_DOTENV_FILENAME = ".env"


@dataclass
class AppConfig:
    repo_root: Path = field(default_factory=Path.cwd)
    base_ref: str = "origin/main"
    output_dir: Path = Path("tests/generated")
    suggestions_dir: Path = Path("reports/suggested-tests")
    report_path: Path = Path("reports/ai-test-report.md")

    source_roots: list[str] = field(default_factory=lambda: ["src", "app", "examples"])
    test_roots: list[str] = field(default_factory=lambda: ["tests"])
    exclude_paths: list[str] = field(
        default_factory=lambda: [
            "tests/generated",
            "reports",
            ".venv",
            "build",
            "dist",
            "migrations",
        ]
    )

    repair_attempts: int = 2
    update_existing_tests: bool = True
    dry_run: bool = False

    google_cloud_project: str | None = None
    google_cloud_location: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    temperature: float = 0.0


def _load_yaml(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    text = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def load_config(
    repo_root: Path | None = None,
    config_path: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> AppConfig:
    """Load configuration from defaults, file, env, and CLI overrides."""
    root = Path(repo_root or Path.cwd()).resolve()
    cfg = AppConfig(repo_root=root)

    # Autoload .env if present so users can keep settings in a local file.
    if _load_dotenv is not None:
        dotenv_path = root / DEFAULT_DOTENV_FILENAME
        if dotenv_path.exists():
            _load_dotenv(dotenv_path, override=False)

    resolved_config_path = config_path or (root / DEFAULT_CONFIG_FILENAME)
    file_data = _load_yaml(resolved_config_path)

    _apply_mapping(cfg, file_data)
    _apply_env(cfg)

    if cli_overrides:
        _apply_mapping(cfg, cli_overrides)

    # Resolve any relative paths against repo_root.
    cfg.output_dir = _ensure_path(cfg.output_dir, root)
    cfg.suggestions_dir = _ensure_path(cfg.suggestions_dir, root)
    cfg.report_path = _ensure_path(cfg.report_path, root)

    return cfg


def _ensure_path(value: Path | str, root: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = (root / path).resolve()
    return path


def _apply_mapping(cfg: AppConfig, data: dict[str, Any]) -> None:
    if not data:
        return

    if "repo_root" in data and data["repo_root"] is not None:
        cfg.repo_root = Path(data["repo_root"]).resolve()
    if "base_ref" in data and data["base_ref"] is not None:
        cfg.base_ref = str(data["base_ref"])
    if "output_dir" in data and data["output_dir"] is not None:
        cfg.output_dir = Path(data["output_dir"])
    if "suggestions_dir" in data and data["suggestions_dir"] is not None:
        cfg.suggestions_dir = Path(data["suggestions_dir"])
    if "report_path" in data and data["report_path"] is not None:
        cfg.report_path = Path(data["report_path"])

    if "source_roots" in data and data["source_roots"] is not None:
        cfg.source_roots = _coerce_list(data["source_roots"])
    if "test_roots" in data and data["test_roots"] is not None:
        cfg.test_roots = _coerce_list(data["test_roots"])
    if "exclude_paths" in data and data["exclude_paths"] is not None:
        cfg.exclude_paths = _coerce_list(data["exclude_paths"])

    if "repair_attempts" in data and data["repair_attempts"] is not None:
        cfg.repair_attempts = int(data["repair_attempts"])
    if "update_existing_tests" in data and data["update_existing_tests"] is not None:
        cfg.update_existing_tests = _coerce_bool(data["update_existing_tests"])
    if "dry_run" in data and data["dry_run"] is not None:
        cfg.dry_run = _coerce_bool(data["dry_run"])

    if "google_cloud_project" in data and data["google_cloud_project"] is not None:
        cfg.google_cloud_project = str(data["google_cloud_project"])
    if "google_cloud_location" in data and data["google_cloud_location"] is not None:
        cfg.google_cloud_location = str(data["google_cloud_location"])
    if "gemini_model" in data and data["gemini_model"] is not None:
        cfg.gemini_model = str(data["gemini_model"])
    if "temperature" in data and data["temperature"] is not None:
        cfg.temperature = float(data["temperature"])


def _apply_env(cfg: AppConfig) -> None:
    env_map = {
        "BASE_REF": "base_ref",
        "OUTPUT_DIR": "output_dir",
        "SUGGESTIONS_DIR": "suggestions_dir",
        "REPORT_PATH": "report_path",
        "REPAIR_ATTEMPTS": "repair_attempts",
        "UPDATE_EXISTING_TESTS": "update_existing_tests",
        "DRY_RUN": "dry_run",
        "GOOGLE_CLOUD_PROJECT": "google_cloud_project",
        "GOOGLE_CLOUD_LOCATION": "google_cloud_location",
        "GEMINI_MODEL": "gemini_model",
        "TEMPERATURE": "temperature",
    }
    overrides: dict[str, Any] = {}
    for env_key, attr in env_map.items():
        if env_key in os.environ and os.environ[env_key] != "":
            overrides[attr] = os.environ[env_key]
    _apply_mapping(cfg, overrides)
