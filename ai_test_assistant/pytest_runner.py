"""Run pytest in a subprocess and return a structured result."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from .models import PytestResult


def run_pytest(
    repo_root: Path,
    paths: list[Path],
    timeout_seconds: int = 120,
) -> PytestResult:
    """Run pytest on the given paths. Failed tests do not raise."""
    cmd = [sys.executable, "-m", "pytest", "-q", *[str(p) for p in paths]]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        duration = time.monotonic() - start
        return PytestResult(
            passed=proc.returncode == 0,
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            duration_seconds=duration,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        return PytestResult(
            passed=False,
            exit_code=-1,
            stdout=(exc.stdout or "").decode("utf-8", errors="ignore")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or ""),
            stderr=f"pytest timed out after {timeout_seconds}s",
            duration_seconds=duration,
        )
