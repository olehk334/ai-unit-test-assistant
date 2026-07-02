"""Order changed files so imported modules are analyzed before their importers.

When a PR changes both ``models.py`` and ``service.py`` (which imports
``models``), analyzing ``service.py`` first would generate tests against a
stale view of its dependency. This module builds the import graph *between the
changed files only* and topologically sorts it with Kahn's algorithm.

On an import cycle the involved files keep their original order and are
reported so the pipeline can note it; a cycle is a code smell but must not
stop test generation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .models import ChangedFile


@dataclass
class ImportOrder:
    ordered_files: list[ChangedFile]
    cycle_files: list[Path] = field(default_factory=list)


def _module_path_for(file_path: Path, repo_root: Path) -> str:
    try:
        rel = file_path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        rel = Path(file_path.name)
    return ".".join(rel.with_suffix("").parts)


def _imported_modules(file_path: Path, repo_root: Path) -> set[str]:
    """Return the absolute module paths imported by ``file_path``."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return set()

    own_module = _module_path_for(file_path, repo_root)
    own_package_parts = own_module.split(".")[:-1]

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imported.add(node.module)
                    # "from calculator import operations" imports the module
                    # calculator.operations, not just the package.
                    for alias in node.names:
                        imported.add(f"{node.module}.{alias.name}")
            else:
                # Relative import: resolve against this file's package.
                base = own_package_parts[: len(own_package_parts) - (node.level - 1)]
                if node.module:
                    imported.add(".".join([*base, node.module]))
                elif base:
                    # "from . import operations" imports siblings by name.
                    for alias in node.names:
                        imported.add(".".join([*base, alias.name]))
    return imported


def order_files_by_imports(
    changed_files: list[ChangedFile],
    repo_root: Path,
) -> ImportOrder:
    """Sort changed files so dependencies come before dependents (Kahn's algorithm)."""
    if len(changed_files) < 2:
        return ImportOrder(ordered_files=list(changed_files))

    module_to_file = {
        _module_path_for(cf.path, repo_root): cf for cf in changed_files
    }

    # Edge dependency -> dependent, restricted to the changed-file set.
    dependents: dict[str, set[str]] = {m: set() for m in module_to_file}
    in_degree: dict[str, int] = {m: 0 for m in module_to_file}
    for module, changed_file in module_to_file.items():
        for imported in _imported_modules(changed_file.path, repo_root):
            if imported in module_to_file and imported != module:
                if module not in dependents[imported]:
                    dependents[imported].add(module)
                    in_degree[module] += 1

    original_position = {m: i for i, m in enumerate(module_to_file)}
    ready = sorted(
        (m for m, degree in in_degree.items() if degree == 0),
        key=original_position.__getitem__,
    )

    ordered_modules: list[str] = []
    while ready:
        module = ready.pop(0)
        ordered_modules.append(module)
        newly_ready = []
        for dependent in dependents[module]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                newly_ready.append(dependent)
        # Keep the output deterministic: original file order breaks ties.
        ready = sorted(ready + newly_ready, key=original_position.__getitem__)

    cycle_modules = [m for m in module_to_file if m not in set(ordered_modules)]
    ordered_modules.extend(cycle_modules)

    return ImportOrder(
        ordered_files=[module_to_file[m] for m in ordered_modules],
        cycle_files=[module_to_file[m].path for m in cycle_modules],
    )
