"""Send a Pub/Sub-shaped test job to a locally running analysis worker.

Usage (worker must be up, e.g. via `docker compose up` in this directory):

    python send_test_job.py
    python send_test_job.py --repeat 5    # demo cache hits on the dashboard
"""

from __future__ import annotations

import argparse
import base64
import json
import urllib.request

def send_job(worker_url: str, clone_url: str, repo_full_name: str) -> str:
    job = {
        "repo_full_name": repo_full_name,
        "clone_url": clone_url,
        "pr_number": 1,
        "head_sha": "HEAD",
        "base_ref": "main",
    }
    envelope = {
        "message": {"data": base64.b64encode(json.dumps(job).encode()).decode()}
    }
    request = urllib.request.Request(
        f"{worker_url}/pubsub",
        data=json.dumps(envelope).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read().decode()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker-url", default="http://localhost:8080")
    # Default: the demo repo docker-compose mounts into the container.
    # Private GitHub URLs will not work — the container has no credentials.
    parser.add_argument("--clone-url", default="/repos/calculator")
    parser.add_argument("--repo-full-name", default="local/calculator")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    for i in range(args.repeat):
        result = send_job(args.worker_url, args.clone_url, args.repo_full_name)
        print(f"job {i + 1}/{args.repeat}: {result}")


if __name__ == "__main__":
    main()
