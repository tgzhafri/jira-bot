# Docker Setup Guide — Atlassian Bot

The project is fully containerized using a multi-stage `Dockerfile` that builds a Streamlit web application image.

## Prerequisites

- Docker 20.10+
- Docker Compose v2+
- A `.env` file with your Jira/Confluence credentials (copy from `.env.example`)

## Quick Start

```bash
# 1. Copy and fill in credentials
cp .env.example .env

# 2. Build and start
make up
# → http://localhost:8501
```

## Commands Reference

```bash
# Lifecycle
make build              # Build the Docker image
make up                 # Start web UI (detached)
make down               # Stop all services
make restart            # Restart the web UI
make logs               # Tail web UI logs

# Development
make shell              # Bash shell inside the container
make test               # Run pytest in the container
make lint               # Run flake8 in the container

# Cleanup
make clean              # Remove containers, images, volumes, generated files
```

## Architecture

```
docker-compose.yml            ← service definition (web)
docker-compose.override.yml   ← dev overrides (source mounts for live reload)
Dockerfile                    ← multi-stage: builder → base → final (Streamlit)
```

### Development Overrides

`docker-compose.override.yml` mounts your local source into the container for live reload during development. For production, run with just the base compose file:

```bash
docker compose -f docker-compose.yml up -d
```

## Volume Mounts

| Host path | Container path | Purpose |
|-----------|---------------|---------|
| `./reports` | `/app/reports` | Persisted report output (CSV/XLSX) |
| `./.cache` | `/app/.cache` | API response cache |
| `./app.py`, `./src/` | `/app/...` | Live reload (dev override only) |

## Environment Variables

Injected via `env_file: .env` in Compose. See `.env.example` for the full list:

```bash
ATLASSIAN_URL=https://your-company.atlassian.net
ATLASSIAN_USERNAME=your-email@company.com
ATLASSIAN_API_TOKEN=your-api-token
ATLASSIAN_PROJECT_KEYS=PROJ1,PROJ2   # optional, empty = all projects
```

## Running Without Compose

```bash
# Build
docker build -t atlassian-bot .

# Run
docker run -d \
  --name atlassian-bot \
  -p 8501:8501 \
  --env-file .env \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/.cache:/app/.cache \
  atlassian-bot
```

## Deployment

### Docker Hub / Registry

```bash
docker build -t youruser/atlassian-bot:latest .
docker push youruser/atlassian-bot:latest
```

### Cloud Platforms (AWS ECS, Cloud Run, Render, etc.)

Point the platform at the `Dockerfile`. Set environment variables in the platform's secrets/config UI rather than mounting `.env`.

### Resource Limits (optional)

Add to `docker-compose.yml` under the `web` service:

```yaml
deploy:
  resources:
    limits:
      cpus: "1"
      memory: 512M
```

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Container won't start | Check `docker compose logs web` and verify `.env` exists |
| Port 8501 in use | Change the host port: `ports: ["8502:8501"]` |
| Stale cache | `rm -rf .cache/*` or `make clean` |
| Permission denied on reports/ | `chmod -R 755 reports/` |
| Build fails on ARM Mac | Add `platform: linux/amd64` under the service |

## Performance

| Scenario | Time |
|----------|------|
| Image build (cold) | ~2–3 min |
| Image build (cached layers) | ~10 s |
| Container startup | ~5 s |
