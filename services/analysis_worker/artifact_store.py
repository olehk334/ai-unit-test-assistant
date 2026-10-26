"""Cloud Storage for job artifacts. A job's prefix (repo/pr/sha) is also its idempotency key."""

from __future__ import annotations

import os
from pathlib import Path

from job_message import AnalysisJob


def report_already_uploaded(job: AnalysisJob) -> bool:
    """Idempotency check: a finished job left its JSON report in GCS."""
    bucket_name = os.environ.get("ARTIFACTS_BUCKET")
    if not bucket_name:
        return False
    from google.cloud import storage

    blob = storage.Client().bucket(bucket_name).blob(
        f"{job.artifact_prefix}/reports/ai-test-report.json"
    )
    return blob.exists()


def upload_artifacts(job: AnalysisJob, clone_dir: Path) -> str | None:
    """Upload reports and generated tests to GCS; return the GCS prefix URL."""
    bucket_name = os.environ.get("ARTIFACTS_BUCKET")
    if not bucket_name:
        return None
    from google.cloud import storage

    bucket = storage.Client().bucket(bucket_name)
    for local_dir in (clone_dir / "reports", clone_dir / "tests" / "generated"):
        if not local_dir.exists():
            continue
        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(clone_dir).as_posix()
            bucket.blob(f"{job.artifact_prefix}/{relative}").upload_from_filename(str(path))
    return f"https://console.cloud.google.com/storage/browser/{bucket_name}/{job.artifact_prefix}"
