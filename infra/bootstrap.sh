#!/usr/bin/env bash
# =============================================================================
# ReliefOps — one-shot GCP + Firebase bootstrap
# Run from repo root after: gcloud auth login && firebase login
# =============================================================================
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-relief-logistics}"
REGION="${REGION:-us-central1}"
FIRESTORE_LOCATION="${FIRESTORE_LOCATION:-nam5}"

echo "→ Linking gcloud to $PROJECT_ID"
gcloud config set project "$PROJECT_ID"

echo "→ Enabling required APIs"
gcloud services enable \
  run.googleapis.com \
  cloudfunctions.googleapis.com \
  pubsub.googleapis.com \
  firestore.googleapis.com \
  firebaseextensions.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  bigquery.googleapis.com \
  routeoptimization.googleapis.com \
  routes.googleapis.com \
  geocoding-backend.googleapis.com \
  maps-backend.googleapis.com \
  aiplatform.googleapis.com \
  generativelanguage.googleapis.com \
  firebaseappcheck.googleapis.com

echo "→ Creating Firestore (multi-region $FIRESTORE_LOCATION)"
gcloud firestore databases create --location="$FIRESTORE_LOCATION" || true

echo "→ Creating Realtime Database instance"
firebase database:instances:create "${PROJECT_ID}-rtdb" --location=us-central1 || true

echo "→ Creating Artifact Registry repo 'relief'"
gcloud artifacts repositories create relief \
  --repository-format=docker --location="$REGION" || true

echo "→ Creating Secret Manager secrets (free tier = 6 secrets)"
for s in gemini-key gmaps-key twilio-token sendgrid-key openweather-key reliefweb-key; do
  gcloud secrets create "$s" --replication-policy=automatic 2>/dev/null || echo "   $s already exists"
done

echo "→ Creating Pub/Sub topics"
for t in shipment.created shipment.status_changed location.updated delay.predicted disruption.detected delivery.completed; do
  gcloud pubsub topics create "$t" 2>/dev/null || echo "   $t already exists"
done

echo "→ Deploying Firestore rules + indexes + storage rules"
firebase deploy --only firestore:rules,firestore:indexes,storage:rules,database --config infra/firebase.json

echo
echo "✔ Bootstrap complete. Next:"
echo "  1. firebase init   # select Hosting, Functions, Extensions, App Check"
echo "  2. firebase ext:install firebase/firestore-bigquery-export"
echo "  3. firebase ext:install twilio/send-message"
echo "  4. firebase ext:install sendgrid/firestore-send-email"
echo "  5. firebase appcheck:apps:register web <APP_ID> --provider=recaptchaEnterprise --site-key=<KEY>"
