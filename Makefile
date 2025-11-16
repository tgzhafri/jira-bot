.PHONY: help build run stop clean logs shell test web web-build web-stop

help: ## Show this help message
	@echo "Automate Jira - Docker Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# CLI Commands
build: ## Build the Docker image
	docker build -t automate-jira:latest .

run: ## Run report generation in container
	docker compose up

stop: ## Stop running containers
	docker compose down

logs: ## View container logs
	docker compose logs -f

shell: ## Open shell in container
	docker run -it --rm --env-file .env -v $(PWD)/reports:/app/reports automate-jira:latest /bin/bash

# Web UI Commands
web: ## Start Streamlit web UI
	docker compose -f docker-compose.streamlit.yml up -d
	@echo ""
	@echo "🚀 Streamlit app running at http://localhost:8501"
	@echo ""

web-build: ## Build and start Streamlit web UI
	docker compose -f docker-compose.streamlit.yml up -d --build
	@echo ""
	@echo "🚀 Streamlit app running at http://localhost:8501"
	@echo ""

web-stop: ## Stop Streamlit web UI
	docker compose -f docker-compose.streamlit.yml down

web-logs: ## View Streamlit logs
	docker compose -f docker-compose.streamlit.yml logs -f

# Utility Commands
clean: ## Remove containers, images, and generated files
	docker compose down -v
	docker compose -f docker-compose.streamlit.yml down -v
	docker rmi automate-jira:latest || true
	rm -rf reports/*.csv .cache/*

test: ## Run tests in container
	docker run --rm -v $(PWD):/app automate-jira:latest pytest

reports-dir: ## Create reports directory
	mkdir -p reports

# Quick start
quick-start: build reports-dir ## Build and run CLI version
	docker compose up
