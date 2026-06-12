# ============================================================
# Medicare Claim Denial Intelligence Platform — Makefile
# ============================================================
# Usage: make <target>
# Run `make help` for a description of all targets.

.DEFAULT_GOAL := help
.PHONY: help up down logs ps restart \
        dbt-run dbt-test dbt-docs dbt-clean \
        ingest download load \
        dashboard install \
        airflow-init airflow-trigger fernet-key \
        clean

# ── Docker ─────────────────────────────────────────────────────────────────────

up:                   ## Start all Docker services in detached mode
	docker-compose up -d

down:                 ## Stop and remove containers (preserves volumes)
	docker-compose down

logs:                 ## Follow logs for all services
	docker-compose logs -f

ps:                   ## Show running container status
	docker-compose ps

restart:              ## Restart all services
	docker-compose restart

# ── dbt ────────────────────────────────────────────────────────────────────────

dbt-run:              ## Run all dbt models
	cd dbt && dbt run

dbt-test:             ## Run all dbt tests
	cd dbt && dbt test

dbt-docs:             ## Generate and serve dbt documentation
	cd dbt && dbt docs generate && dbt docs serve

dbt-clean:            ## Remove dbt target/ and dbt_packages/
	cd dbt && dbt clean

dbt-staging:          ## Run only staging layer models
	cd dbt && dbt run --select staging

dbt-staging-test:     ## Test only staging layer
	cd dbt && dbt test --select staging

# ── Data Ingestion ─────────────────────────────────────────────────────────────

ingest:               ## Download CMS data AND load to PostgreSQL
	python ingestion/scripts/download_cms_data.py
	python ingestion/scripts/load_to_postgres.py

download:             ## Download CMS CSVs only
	python ingestion/scripts/download_cms_data.py

load:                 ## Load downloaded CSVs to PostgreSQL only
	python ingestion/scripts/load_to_postgres.py

# ── Dashboard ──────────────────────────────────────────────────────────────────

dashboard:            ## Launch Streamlit dashboard
	streamlit run streamlit/app.py

# ── Python environment ─────────────────────────────────────────────────────────

install:              ## Install Python dependencies from requirements.txt
	pip install -r requirements.txt

# ── Airflow helpers ────────────────────────────────────────────────────────────

airflow-init:         ## Re-initialize Airflow DB and admin user (first run)
	docker-compose run --rm airflow-init

airflow-trigger:      ## Manually trigger the cms_daily_ingest DAG
	docker exec denial_airflow_scheduler airflow dags trigger cms_daily_ingest

# ── Utilities ──────────────────────────────────────────────────────────────────

fernet-key:           ## Generate a new Airflow Fernet key (paste into .env)
	python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

clean:                ## Remove __pycache__, .pyc files, and dbt target
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	cd dbt && dbt clean 2>/dev/null || true

# ── Help ───────────────────────────────────────────────────────────────────────

help:                 ## Show this help message
	@echo ""
	@echo "Medicare Claim Denial Intelligence Platform"
	@echo "============================================"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""
