"""Find existing pytest test files related to a changed source file."""

from __future__ import annotations

from pathlib import Path

from .models import TestTarget


def _candidate_paths(source_file: Path, repo_root: Path, test_roots: list[str]) -> list[Path]:
    """Return likely test file paths derived from the source file name."""
    try:
        rel = source_file.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = Path(source_file.name)

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
    try:
        rel = source_file.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return []

    module_parts = list(rel.with_suffix("").parts)
    module_dotted = ".".join(module_parts)
    module_stem = rel.stem

    needles: set[str] = {module_dotted, module_stem}
    for target in targets:
        needles.add(target.name)
        if "." in target.qualified_name:
            needles.add(target.qualified_name.split(".", 1)[0])

    matches: list[Path] = []
    for root_name in test_roots:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            name = path.name
            if not (name.startswith("test_") or name.endswith("_test.py")):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(needle and needle in text for needle in needles):
                matches.append(path)
    return matches


def find_related_tests(
    source_file: Path,
    targets: list[TestTarget],
    repo_root: Path,
    test_roots: list[str],
) -> list[Path]:
    """Return unique existing test files related to ``source_file``."""
    found: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(resolved)

    for candidate in _candidate_paths(source_file, repo_root, test_roots):
        if candidate.exists() and candidate.is_file():
            _add(candidate)

    for path in _scan_for_references(source_file, targets, repo_root, test_roots):
        _add(path)

    return found
