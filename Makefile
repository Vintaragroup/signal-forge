PYTHON ?= python3
BUSINESS_TYPE ?= roofing contractor
LOCATION ?= Austin, TX
LEAD_COUNT ?= 5

.PHONY: up down api web dashboard pipeline report revenue-report check test gpt-agent-test

up:
	docker compose up -d --build

down:
	docker compose down

api:
	docker compose up -d --build api

web:
	docker compose up -d --build web

dashboard:
	docker compose up -d --build api web

pipeline:
	BUSINESS_TYPE="$(BUSINESS_TYPE)" LOCATION="$(LOCATION)" LEAD_COUNT="$(LEAD_COUNT)" ./scripts/run_daily_pipeline.sh

report:
	$(PYTHON) scripts/generate_pipeline_report.py

revenue-report:
	$(PYTHON) scripts/generate_revenue_report.py

check:
	docker compose run --rm api python scripts/check_system.py

test:
	docker compose run --rm --no-deps api python -m pytest

gpt-agent-test:
	docker compose run --rm api python scripts/gpt_runtime_test_campaign.py
