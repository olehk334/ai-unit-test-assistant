"""Path rules every step shares: where a file sits in the repo, and what a test file is."""

from __future__ import annotations

from pathlib import Path


def relative_to_repo(path: Path, repo_root: Path) -> Path | None:
    resolved, root = path.resolve(), repo_root.resolve()
    return resolved.relative_to(root) if resolved.is_relative_to(root) else None


def module_name(path: Path, repo_root: Path) -> str:
    rel = relative_to_repo(path, repo_root) or Path(path.name)
    return ".".join(rel.with_suffix("").parts)


def is_test_file_name(name: str) -> bool:
    return name.startswith("test_") or name.endswith("_test.py")


def is_generated_file_name(name: str) -> bool:
    return name.endswith("_generated.py")
