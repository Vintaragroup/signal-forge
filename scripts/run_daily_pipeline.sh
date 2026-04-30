#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BUSINESS_TYPE="${BUSINESS_TYPE:-roofing contractor}"
LOCATION="${LOCATION:-Austin, TX}"
LEAD_COUNT="${LEAD_COUNT:-5}"
PIPELINE_RUN_ID="${PIPELINE_RUN_ID:-$(date -u +"%Y%m%dT%H%M%SZ")}"
LEAD_SOURCE_FILE="${LEAD_SOURCE_FILE:-/data/raw/contractor_listings_seed.json}"

usage() {
  cat <<USAGE
Usage: ./scripts/run_daily_pipeline.sh [options]

Options:
  --business-type VALUE   Business type to import, default: roofing contractor
  --location VALUE        Location to import, default: Austin, TX
  --count VALUE           Maximum listings to import, default: 5
  --run-id VALUE          Optional run id, default: current UTC timestamp
  --data-file VALUE       Container path to listing dataset, default: /data/raw/contractor_listings_seed.json
  -h, --help              Show this help

Environment variables are also supported:
  BUSINESS_TYPE, LOCATION, LEAD_COUNT, PIPELINE_RUN_ID, LEAD_SOURCE_FILE
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --business-type)
      BUSINESS_TYPE="$2"
      shift 2
      ;;
    --location)
      LOCATION="$2"
      shift 2
      ;;
    --count)
      LEAD_COUNT="$2"
      shift 2
      ;;
    --run-id)
      PIPELINE_RUN_ID="$2"
      shift 2
      ;;
    --data-file)
      LEAD_SOURCE_FILE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

echo "Running signalForge Contractor Lead Engine pipeline..."
echo "Run ID: ${PIPELINE_RUN_ID}"
echo "Business type: ${BUSINESS_TYPE}"
echo "Location: ${LOCATION}"
echo "Lead count: ${LEAD_COUNT}"
echo "Lead source file: ${LEAD_SOURCE_FILE}"

if [ ! -f ".env" ]; then
  echo "No .env file found. Using .env.example defaults and blank optional secrets."
fi

docker compose run --rm \
  -e BUSINESS_TYPE="${BUSINESS_TYPE}" \
  -e LOCATION="${LOCATION}" \
  -e LEAD_COUNT="${LEAD_COUNT}" \
  -e PIPELINE_RUN_ID="${PIPELINE_RUN_ID}" \
  -e LEAD_SOURCE_FILE="${LEAD_SOURCE_FILE}" \
  lead_scraper

docker compose run --rm \
  -e BUSINESS_TYPE="${BUSINESS_TYPE}" \
  -e LOCATION="${LOCATION}" \
  -e PIPELINE_RUN_ID="${PIPELINE_RUN_ID}" \
  lead_enricher

echo "Contractor Lead Engine pipeline complete."
echo "Review vault/leads, vault/companies, vault/review_queue, and vault/logs."
