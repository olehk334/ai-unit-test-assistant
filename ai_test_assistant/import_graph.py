"""Order changed files so imported modules come before the files that import them.

Kahn's algorithm over the import graph between the changed files only. The
ready files sit in a min-heap keyed by their original position, so among the
files whose dependencies are done, the one listed first goes next and the
order is reproducible: O((V + E) log V) for V files and E imports.

What the order changes: the report lists a module before the code that uses
it, and a module is processed before tests exist for its importers. Generated
tests land under tests/, which the related-test search reads, so tests written
in this run for an importer cannot leak into the module's prompt.

Files in an import cycle keep their original order and are reported: a cycle
is a code smell in the analyzed repo, not a reason to stop generating tests.
"""

from __future__ import annotations

import ast
import heapq
from dataclasses import dataclass, field
from pathlib import Path

from .models import ChangedFile
from .repo_paths import module_name


@dataclass
class ImportOrder:
    ordered_files: list[ChangedFile]
    cycle_files: list[Path] = field(default_factory=list)


def _imported_modules(file_path: Path, repo_root: Path) -> set[str]:
    """Return the absolute module paths imported by ``file_path``."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return set()

    own_module = module_name(file_path, repo_root)
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
        module_name(cf.path, repo_root): cf for cf in changed_files
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
    ready = [(original_position[m], m) for m, degree in in_degree.items() if degree == 0]
    heapq.heapify(ready)

    ordered_modules: list[str] = []
    while ready:
        _, module = heapq.heappop(ready)
        ordered_modules.append(module)
        for dependent in dependents[module]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                heapq.heappush(ready, (original_position[dependent], dependent))

    ordered = set(ordered_modules)
    cycle_modules = [m for m in module_to_file if m not in ordered]
    ordered_modules.extend(cycle_modules)

    return ImportOrder(
        ordered_files=[module_to_file[m] for m in ordered_modules],
        cycle_files=[module_to_file[m].path for m in cycle_modules],
    )
