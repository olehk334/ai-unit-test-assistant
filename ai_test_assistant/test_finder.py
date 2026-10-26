"""Find existing pytest test files related to a changed source file."""

from __future__ import annotations

import re
from pathlib import Path

from .models import TestTarget
from .repo_paths import is_generated_file_name, is_test_file_name, relative_to_repo


def _candidate_paths(source_file: Path, repo_root: Path, test_roots: list[str]) -> list[Path]:
    """Return likely test file paths derived from the source file name."""
    rel = relative_to_repo(source_file, repo_root) or Path(source_file.name)

    stem = rel.stem
    candidates: list[Path] = []

    for root_name in test_roots:
        root = repo_root / root_name
        # Direct: tests/test_<stem>.py
        candidates.append(root / f"test_{stem}.py")
        # Mirror: tests/<source-parents>/test_<stem>.py
        if len(rel.parts) > 1:
            mirrored = root.joinpath(*rel.parent.parts) / f"test_{stem}.py"
            candidates.append(mirrored)
        # Alt suffix: tests/<stem>_test.py
        candidates.append(root / f"{stem}_test.py")

    return candidates


def _scan_for_references(
    source_file: Path,
    targets: list[TestTarget],
    repo_root: Path,
    test_roots: list[str],
) -> list[Path]:
    """Scan test directories for files that import or mention this source."""
    rel = relative_to_repo(source_file, repo_root)
    if rel is None:
        return []

    module_parts = list(rel.with_suffix("").parts)
    module_dotted = ".".join(module_parts)
    module_stem = rel.stem

    needles: set[str] = {module_dotted, module_stem}
    for target in targets:
        needles.add(target.name)
        if "." in target.qualified_name:
            needles.add(target.qualified_name.split(".", 1)[0])

    # Word boundaries so a target named "add" does not match "address".
    reference_pattern = re.compile(
        "|".join(rf"\b{re.escape(needle)}\b" for needle in sorted(needles) if needle)
    )

    matches: list[Path] = []
    for root_name in test_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            # Generated tests are the assistant's own output, not existing tests:
            # as context they would feed earlier answers back into its prompts.
            if not is_test_file_name(path.name) or is_generated_file_name(path.name):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if reference_pattern.search(text):
                matches.append(path)
    return matches


def find_related_tests(
    source_file: Path,
    targets: list[TestTarget],
    repo_root: Path,
    test_roots: list[str],
) -> list[Path]:
    """Return unique existing test files related to ``source_file``."""
    by_name = [
        candidate
        for candidate in _candidate_paths(source_file, repo_root, test_roots)
        if candidate.is_file()
    ]
    by_reference = _scan_for_references(source_file, targets, repo_root, test_roots)
    return list(dict.fromkeys(path.resolve() for path in by_name + by_reference))


def read_test_files(paths: list[Path]) -> dict[Path, str]:
    contents: dict[Path, str] = {}
    for path in paths:
        try:
            contents[path] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    return contents
