# Docker Setup Guide - Automate Jira

This project is fully containerized with Docker for easy deployment and consistent environments.

## Quick Start

### Option 1: CLI Report Generation

```bash
# Build the image
make build

# Run report generation
make run

# Output will be in ./reports/manhour_report_2025.csv
```

### Option 2: Web UI (Recommended)

```bash
# Start Streamlit web interface
make web

# Open browser to http://localhost:8501
# Click "Generate Report" button
# Download CSV directly from browser
```

## Prerequisites

- Docker (20.10+)
- Docker Compose (2.0+)
- `.env` file with Jira credentials

## Available Commands

### CLI Commands
```bash
make build          # Build Docker image
make run            # Generate report in container
make stop           # Stop containers
make logs           # View logs
make shell          # Open bash shell in container
```

### Web UI Commands
```bash
make web            # Start Streamlit app (http://localhost:8501)
make web-build      # Rebuild and start Streamlit app
make web-stop       # Stop Streamlit app
make web-logs       # View Streamlit logs
```

### Utility Commands
```bash
make clean          # Remove containers, images, and reports
make test           # Run tests in container
make help           # Show all commands
```

## Configuration

### Environment Variables

Create a `.env` file:

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=PROJ1,PROJ2  # Optional: leave empty for all projects
JIRA_ENABLE_CACHE=true
JIRA_MAX_WORKERS=8
```

### Volume Mounts

The containers mount these directories:

- `./reports` - Generated CSV files persist here
- `./.cache` - API response cache for faster runs
- `./app.py` - Hot reload for Streamlit development

## Docker Images

### CLI Image (Dockerfile)
- **Base:** python:3.11-slim
- **Size:** ~200MB
- **Purpose:** Run report generation script
- **Entry:** `python scripts/generate_report.py`

### Web UI Image (Dockerfile.streamlit)
- **Base:** python:3.11-slim
- **Size:** ~250MB
- **Purpose:** Streamlit web interface
- **Port:** 8501
- **Entry:** `streamlit run app.py`

## Usage Examples

### Generate Report for Specific Year

```bash
# Using CLI
docker run --rm --env-file .env \
  -v $(pwd)/reports:/app/reports \
  automate-jira:latest

# Using Web UI - select year in sidebar
make web
```

### Run Without Docker Compose

```bash
# Build
docker build -t automate-jira:latest .

# Run CLI
docker run --rm \
  --env-file .env \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/.cache:/app/.cache \
  automate-jira:latest

# Run Web UI
docker run -d \
  --name automate-jira-web \
  -p 8501:8501 \
  --env-file .env \
  -v $(pwd)/reports:/app/reports \
  -v $(pwd)/.cache:/app/.cache \
  -f Dockerfile.streamlit \
  automate-jira:latest
```

### Debug Inside Container

```bash
# Open shell
make shell

# Or manually
docker run -it --rm \
  --env-file .env \
  -v $(pwd)/reports:/app/reports \
  automate-jira:latest /bin/bash

# Inside container
python scripts/generate_report.py
ls -la reports/
```

## Deployment Options

### 1. Local Development
```bash
make web  # Run on localhost:8501
```

### 2. Docker Hub
```bash
# Tag and push
docker tag automate-jira:latest youruser/automate-jira:latest
docker push youruser/automate-jira:latest

# Pull and run anywhere
docker pull youruser/automate-jira:latest
docker run -d -p 8501:8501 --env-file .env youruser/automate-jira:latest
```

### 3. Cloud Deployment

**AWS ECS/Fargate:**
```bash
# Push to ECR
aws ecr get-login-password | docker login --username AWS --password-stdin <account>.dkr.ecr.region.amazonaws.com
docker tag automate-jira:latest <account>.dkr.ecr.region.amazonaws.com/automate-jira:latest
docker push <account>.dkr.ecr.region.amazonaws.com/automate-jira:latest
```

**Google Cloud Run:**
```bash
# Push to GCR
docker tag automate-jira:latest gcr.io/<project>/automate-jira:latest
docker push gcr.io/<project>/automate-jira:latest
gcloud run deploy automate-jira --image gcr.io/<project>/automate-jira:latest
```

**Render/Railway/Fly.io:**
- Connect GitHub repo
- Select `Dockerfile.streamlit`
- Add environment variables
- Deploy

### 4. Kubernetes
```bash
# Create deployment
kubectl create deployment automate-jira --image=automate-jira:latest
kubectl expose deployment automate-jira --port=8501 --type=LoadBalancer
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs

# Verify .env file
cat .env

# Test connection
docker run --rm --env-file .env automate-jira:latest python -c "from src.config import Config; Config.from_env().validate()"
```

### Permission issues
```bash
# Fix reports directory permissions
chmod -R 755 reports/
```

### Cache issues
```bash
# Clear cache
rm -rf .cache/*

# Or rebuild without cache
docker-compose build --no-cache
```

### Port already in use
```bash
# Change port in docker-compose.streamlit.yml
ports:
  - "8502:8501"  # Use 8502 instead
```

## Performance

- **First run:** ~20-30s (fetching from Jira)
- **Cached run:** ~2-5s (using local cache)
- **Image build:** ~2-3 minutes
- **Container startup:** ~5-10s

## Security Notes

- Never commit `.env` file
- Use Docker secrets for production
- Limit container resources if needed:
  ```yaml
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 512M
  ```

## Next Steps

1. **Try it:** `make web` and open http://localhost:8501
2. **Deploy:** Push to Docker Hub or cloud platform
3. **Customize:** Edit `app.py` for UI changes
4. **Scale:** Use Kubernetes or cloud auto-scaling

---

**Need help?** Check the main README.md or open an issue.
