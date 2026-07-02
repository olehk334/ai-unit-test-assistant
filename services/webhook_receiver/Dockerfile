FROM python:3.12-slim

WORKDIR /app
COPY services/webhook_receiver/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/webhook_receiver/receiver_app.py .

# Cloud Run provides $PORT; default to 8080 for local runs.
ENV PORT=8080
CMD ["sh", "-c", "uvicorn receiver_app:app --host 0.0.0.0 --port ${PORT}"]
