# Quick Start Guide - Automate Jira

## 🚀 Get Started in 2 Minutes

### Prerequisites
- Docker installed
- Jira API credentials

### Step 1: Configure
Create `.env` file in project root:
```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your-api-token
```

Get API token: https://id.atlassian.com/manage-profile/security/api-tokens

### Step 2: Run
```bash
make web
```

### Step 3: Use
1. Open http://localhost:8501 in your browser
2. Select year (defaults to current year)
3. Click "🚀 Generate Report"
4. View table preview with metrics
5. Click "📥 Download CSV Report"

Done! 🎉

---

## Common Commands

```bash
make web          # Start web UI
make web-stop     # Stop web UI
make web-logs     # View logs
make web-build    # Rebuild and start
make help         # See all commands
```

## What You Get

**Web Interface:**
- Interactive table preview
- Summary metrics (rows, team members, total hours)
- Year selection
- Advanced options (parallel workers, cache settings)
- One-click CSV download

**CSV Report Format:**
```csv
Project,Component,John Doe,Jane Smith,Bob Wilson
ERP,HR,40.0,8.0,
ERP,Recruitment,24.0,12.0,8.0
```

## Troubleshooting

**Container won't start:**
```bash
make web-logs  # Check logs
```

**Need to rebuild:**
```bash
make web-stop
make web-build
```

**Clear cache:**
```bash
rm -rf .cache/*
make web-stop
make web
```

## Next Steps

- Read [README.md](README.md) for detailed features
- Check [docs/DOCKER.md](docs/DOCKER.md) for deployment options
- See [CHANGELOG.md](CHANGELOG.md) for version history

---

**Questions?** Check the documentation or open an issue.
