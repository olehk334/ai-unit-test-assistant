# Build from the repository root so the assistant package can be installed:
#   docker build -f services/analysis_worker/Dockerfile -t analysis-worker .
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The worker runs the assistant as a library; install it with its deps.
COPY pyproject.toml README.md ./
COPY ai_test_assistant ./ai_test_assistant
RUN pip install --no-cache-dir .

COPY services/analysis_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/analysis_worker/*.py ./

ENV PORT=8080
CMD ["sh", "-c", "uvicorn worker_app:app --host 0.0.0.0 --port ${PORT}"]
