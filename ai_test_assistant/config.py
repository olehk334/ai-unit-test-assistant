"""Application configuration loading.

Priority (highest first):
    CLI args > environment variables > config file > defaults
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


DEFAULT_CONFIG_FILENAME = "ai-test-assistant.yml"
DEFAULT_DOTENV_FILENAME = ".env"


@dataclass
class AppConfig:
    repo_root: Path = field(default_factory=Path.cwd)
    base_ref: str = "origin/main"
    output_dir: Path = Path("tests/generated")
    suggestions_dir: Path = Path("reports/suggested-tests")
    report_path: Path = Path("reports/ai-test-report.md")

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
    """Load configuration from defaults, file, env, and CLI overrides.

    Side effect: if ``<repo_root>/.env`` exists, its values are loaded into
    ``os.environ`` (without overriding variables that are already set) so the
    normal env-var precedence picks them up.
    """
    root = Path(repo_root or Path.cwd()).resolve()
    cfg = AppConfig(repo_root=root)

    # Autoload .env if present so users can keep settings in a local file.
    dotenv_path = root / DEFAULT_DOTENV_FILENAME
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=False)

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


# repo_root is not a setting: the caller decides which repository a run is about.
_SETTING_PARSERS: dict[str, Callable[[Any], Any]] = {
    "base_ref": str,
    "output_dir": Path,
    "suggestions_dir": Path,
    "report_path": Path,
    "test_roots": _coerce_list,
    "exclude_paths": _coerce_list,
    "repair_attempts": int,
    "update_existing_tests": _coerce_bool,
    "dry_run": _coerce_bool,
    "google_cloud_project": str,
    "google_cloud_location": str,
    "gemini_model": str,
    "temperature": float,
}

# Each of these settings can also come from the environment, named in upper case
# (dry_run <- DRY_RUN).
_ENV_SETTINGS = (
    "base_ref",
    "output_dir",
    "suggestions_dir",
    "report_path",
    "repair_attempts",
    "update_existing_tests",
    "dry_run",
    "google_cloud_project",
    "google_cloud_location",
    "gemini_model",
    "temperature",
)


def _apply_mapping(cfg: AppConfig, data: dict[str, Any]) -> None:
    for name, parse in _SETTING_PARSERS.items():
        value = data.get(name)
        if value is not None:
            setattr(cfg, name, parse(value))


def _apply_env(cfg: AppConfig) -> None:
    overrides = {
        name: os.environ[name.upper()]
        for name in _ENV_SETTINGS
        if os.environ.get(name.upper())
    }
    _apply_mapping(cfg, overrides)
