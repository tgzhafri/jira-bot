.PHONY: help build up down logs restart shell test lint clean

help: ## Show this help message
	@echo "Atlassian Bot — Docker Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Core lifecycle
# ---------------------------------------------------------------------------
build: ## Build the Docker image
	docker compose build

up: ## Start the web UI (detached)
	docker compose up -d
	@echo ""
	@echo "🚀 Streamlit app running at http://localhost:8501"
	@echo ""

down: ## Stop all running services
	docker compose down

restart: ## Restart the web UI
	docker compose restart web

logs: ## Tail web UI logs
	docker compose logs -f web

# ---------------------------------------------------------------------------
# Development helpers
# ---------------------------------------------------------------------------
shell: ## Open a bash shell in the web container
	docker compose exec web /bin/bash

test: ## Run pytest inside a container
	docker compose exec web python -m pytest

lint: ## Run linters inside a container
	docker compose exec web python -m flake8 src/

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------
clean: ## Remove containers, images, volumes, and generated files
	docker compose down -v --rmi local
	rm -rf reports/*.csv reports/*.xlsx .cache/*
