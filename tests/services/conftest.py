"""Make the standalone service apps importable from the test suite.

The services are deployables, not installable packages, so their directories
are added to sys.path here. Module names are unique (receiver_app,
worker_app) to avoid import collisions.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
for service_dir in (
    _REPO_ROOT / "services" / "webhook_receiver",
    _REPO_ROOT / "services" / "analysis_worker",
):
    if str(service_dir) not in sys.path:
        sys.path.insert(0, str(service_dir))
