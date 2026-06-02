"""Git helpers for detecting changed Python files and changed line ranges."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

from .models import ChangedFile


_EXCLUDED_NAME_PATTERNS = (
    re.compile(r"^test_.*\.py$"),
    re.compile(r".*_test\.py$"),
    re.compile(r".*_generated\.py$"),
)

_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def is_production_python_file(path: Path, exclude_paths: list[str]) -> bool:
    """Return True if ``path`` represents a production Python file we should analyze."""
    if path.suffix != ".py":
        return False

    posix = PurePosixPath(*path.parts).as_posix()
    parts = path.parts

    # Filter by name patterns (test files, generated files).
    if any(pat.match(path.name) for pat in _EXCLUDED_NAME_PATTERNS):
        return False

    # Filter by directory-style exclusions.
    if "tests" in parts:
        return False
    for excluded in exclude_paths:
        norm = excluded.replace("\\", "/").strip("/")
        if not norm:
            continue
        if posix == norm or posix.startswith(norm + "/"):
            return False

    return True


def _run_git(args: list[str], repo_root: Path) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # Surface a clean error so callers can decide how to handle it.
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    return result.stdout


def _list_changed_file_names(repo_root: Path, base_ref: str) -> list[str]:
    output = _run_git(["diff", "--name-only", f"{base_ref}...HEAD"], repo_root)
    return [line.strip() for line in output.splitlines() if line.strip()]


def _parse_changed_lines(repo_root: Path, base_ref: str, file_path: str) -> set[int]:
    """Return the set of line numbers (in the new file) that changed."""
    try:
        output = _run_git(
            ["diff", "--unified=0", f"{base_ref}...HEAD", "--", file_path],
            repo_root,
        )
    except RuntimeError:
        return set()

    changed: set[int] = set()
    for line in output.splitlines():
        match = _HUNK_HEADER_RE.match(line)
        if not match:
            continue
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) else 1
        if count == 0:
            continue
        for n in range(start, start + count):
            changed.add(n)
    return changed


def get_changed_python_files(
    repo_root: Path,
    base_ref: str,
    exclude_paths: list[str],
) -> list[ChangedFile]:
    """Return the list of changed production Python files since ``base_ref``."""
    try:
        names = _list_changed_file_names(repo_root, base_ref)
    except RuntimeError:
        return []

    results: list[ChangedFile] = []
    for name in names:
        rel = Path(name)
        full = repo_root / rel
        if not full.exists():
            continue
        if not is_production_python_file(rel, exclude_paths):
            continue
        changed_lines = _parse_changed_lines(repo_root, base_ref, name)
        results.append(ChangedFile(path=full, changed_lines=changed_lines))
    return results
