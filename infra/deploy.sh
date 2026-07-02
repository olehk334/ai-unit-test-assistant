#!/usr/bin/env bash
# Deploy the AI Test Assistant platform to GCP.
#
# COSTS MONEY / CREATES RESOURCES — run only when you mean it.
# Everything is scale-to-zero or pay-per-use; at demo volume the cost is
# effectively the Gemini calls themselves.
#
# Prerequisites:
#   gcloud auth login              (personal account)
#   gcloud config set project ai-test-assistant-demo
#   GITHUB_WEBHOOK_SECRET exported (any random string; also set on GitHub)
#   GITHUB_TOKEN exported          (optional, for commit statuses)
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project)"
REGION="us-central1"
TOPIC="pr-analysis-jobs"
DEAD_LETTER_TOPIC="pr-analysis-jobs-dead-letter"
BUCKET="${PROJECT_ID}-ai-test-artifacts"
REPO="ai-test-assistant"

echo "Deploying to project: ${PROJECT_ID}"

# --- APIs -------------------------------------------------------------------
gcloud services enable \
  run.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

# --- Artifact Registry for container images ----------------------------------
gcloud artifacts repositories describe "${REPO}" --location="${REGION}" 2>/dev/null || \
gcloud artifacts repositories create "${REPO}" \
  --repository-format=docker --location="${REGION}"

IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

# --- Build images (from the repository root) ---------------------------------
# `gcloud builds submit --tag` cannot point at a custom Dockerfile path,
# so each service has a small Cloud Build config that can.
gcloud builds submit --config infra/cloudbuild-receiver.yaml \
  --substitutions "_IMAGE=${IMAGE_BASE}/webhook-receiver" .
gcloud builds submit --config infra/cloudbuild-worker.yaml \
  --substitutions "_IMAGE=${IMAGE_BASE}/analysis-worker" .

# --- Pub/Sub topics -----------------------------------------------------------
gcloud pubsub topics describe "${TOPIC}" 2>/dev/null || \
  gcloud pubsub topics create "${TOPIC}"
gcloud pubsub topics describe "${DEAD_LETTER_TOPIC}" 2>/dev/null || \
  gcloud pubsub topics create "${DEAD_LETTER_TOPIC}"

# --- Artifacts bucket ----------------------------------------------------------
gsutil ls -b "gs://${BUCKET}" 2>/dev/null || gsutil mb -l "${REGION}" "gs://${BUCKET}"

# --- Analysis worker (private; only Pub/Sub may call it) ----------------------
gcloud run deploy analysis-worker \
  --image "${IMAGE_BASE}/analysis-worker" \
  --region "${REGION}" \
  --no-allow-unauthenticated \
  --concurrency 1 \
  --memory 1Gi \
  --timeout 600 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${REGION},GEMINI_MODEL=gemini-2.5-flash,ARTIFACTS_BUCKET=${BUCKET},GITHUB_TOKEN=${GITHUB_TOKEN:-}"

WORKER_URL="$(gcloud run services describe analysis-worker --region "${REGION}" --format 'value(status.url)')"

# --- Push subscription with retries and dead-lettering -------------------------
PUSH_SA="pubsub-pusher@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts describe "${PUSH_SA}" 2>/dev/null || \
  gcloud iam service-accounts create pubsub-pusher --display-name "Pub/Sub push auth"
gcloud run services add-iam-policy-binding analysis-worker \
  --region "${REGION}" \
  --member "serviceAccount:${PUSH_SA}" \
  --role roles/run.invoker

gcloud pubsub subscriptions describe pr-analysis-push 2>/dev/null || \
gcloud pubsub subscriptions create pr-analysis-push \
  --topic "${TOPIC}" \
  --push-endpoint "${WORKER_URL}/pubsub" \
  --push-auth-service-account "${PUSH_SA}" \
  --ack-deadline 600 \
  --dead-letter-topic "${DEAD_LETTER_TOPIC}" \
  --max-delivery-attempts 5

# --- Webhook receiver (public; GitHub must reach it) ---------------------------
gcloud run deploy webhook-receiver \
  --image "${IMAGE_BASE}/webhook-receiver" \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars "PUBSUB_TOPIC=projects/${PROJECT_ID}/topics/${TOPIC},GITHUB_WEBHOOK_SECRET=${GITHUB_WEBHOOK_SECRET}"

RECEIVER_URL="$(gcloud run services describe webhook-receiver --region "${REGION}" --format 'value(status.url)')"

echo ""
echo "Done. Configure the GitHub webhook on the target repo:"
echo "  Payload URL:  ${RECEIVER_URL}/webhook"
echo "  Content type: application/json"
echo "  Secret:       \$GITHUB_WEBHOOK_SECRET"
echo "  Events:       Pull requests"
