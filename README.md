# Automate Jira

> Professional time tracking and reporting tool for Jira

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 🌐 **Web UI** - Interactive Streamlit interface with one-click report generation
- 🐳 **Docker Ready** - Fully containerized for easy deployment anywhere
- 📊 **Multiple Report Types** - Yearly overview, quarterly, monthly, and weekly breakdowns
- 👤 **User Filtering** - Generate reports for all users or specific individuals
- 📅 **Time Breakdowns** - View hours by year, quarter, month, or week
- 📁 **Project Selection** - Filter reports by specific projects
- 📋 **Table Preview** - View reports in proper table format before downloading
- 📑 **Multi-level Headers** - XLSX exports with organized, readable headers
- ⚡ **High Performance** - Parallel processing, caching, and optimized API calls (70-90% faster)
- 💾 **Smart Caching** - Instant re-runs with automatic response caching
- 🏗️ **Modular Architecture** - Clean, maintainable code structure
- 🔒 **Type Safe** - Full type hints throughout

## Quick Start

> **New to this?** Check [QUICK_START.md](QUICK_START.md) for a 2-minute setup guide.

### Option 1: Docker (Recommended)

```bash
# Start web UI with one command
make up

# Open browser to http://localhost:8501
# Click "Generate Report" button → View table → Download CSV
```

See [docs/DOCKER.md](docs/DOCKER.md) for full Docker documentation.

### Option 2: Local Installation

```bash
# Clone and setup
git clone <repo-url>
cd automate-jira
python3 -m venv venv
source venv/bin/activate

# Install
pip install -e .

# Run
streamlit run app.py
```

### Configuration

Create `.env` file:

```bash
ATLASSIAN_URL=https://your-company.atlassian.net
ATLASSIAN_USERNAME=your-email@company.com
ATLASSIAN_API_TOKEN=your-api-token
# ATLASSIAN_PROJECT_KEYS=PROJ1,PROJ2  # Optional: leave empty to fetch all projects
```

Get your API token: https://id.atlassian.com/manage-profile/security/api-tokens

**Note**: If `ATLASSIAN_PROJECT_KEYS` is not set or empty, the tool will automatically fetch all accessible projects.

## Output Format

### CSV Team Overview (All Users)

```csv
Project,Component,John Doe,Jane Smith,Bob Wilson
ERP,HR,40.0,8.0,
ERP,Recruitment,24.0,12.0,8.0
Client Portal,Core,4.0,2.0,
```

- **One row** per project-component combination
- **One column** per team member
- **Hours** aggregated for the entire year
- **Excel/Sheets ready** - import directly

### Monthly Breakdown (Per Team Member)

```csv
Team Member,Work Type,Project,Component,Jan,Feb,Mar,...,Dec,Total
John Doe,Development,ERP,HR,5.0,8.0,12.0,...,0.0,40.0
John Doe,Development,ERP,Recruitment,2.0,4.0,6.0,...,0.0,24.0
```

- **One sheet per team member** (XLSX format)
- **Separate sections** for Development and Maintenance
- **12 month columns** (Jan-Dec) plus Total
- **Summary rows** with monthly and grand totals

### Weekly Breakdown (Per Team Member)

```csv
Team Member,Work Type,Project,Component,JanW1,JanW2,...,DecW5,Total
John Doe,Development,ERP,HR,2.0,1.5,1.5,...,0.0,40.0
```

- **One sheet per team member** (XLSX format)
- **Multi-level headers** in XLSX: Month names spanning 5 week columns
- **60 week columns** (5 weeks × 12 months) plus Total
- **Week calculation**: Based on day of month (1-7=W1, 8-14=W2, etc.)
- **Separate sections** for Development and Maintenance

## Usage

### Web UI

The Streamlit web interface provides:

- **Dashboard** — Connection status and quick overview
- **Manhour Aggregator** — Generate and preview reports with filters
- **Jira Backup** — Export project data to ZIP archives
- **Confluence Backup** — Export Confluence spaces
- **Settings** — Configure Jira connection credentials

### As Library

```python
from src.config import Config
from src.services.jira_client import JiraClient
from src.exporters import TeamOverviewExporter
from pathlib import Path

# Load config
config = Config.from_env()

# Fetch data
client = JiraClient(config.jira)
issues = client.get_issues_with_worklog(...)

# Export
exporter = TeamOverviewExporter(Path("report.csv"))
exporter.export_yearly(report)
```

## Project Structure

```
automate-jira/
├── app.py                 # Web UI entry point (Streamlit)
├── src/                   # Core business logic
│   ├── config.py          # Configuration
│   ├── models/            # Data models
│   ├── services/          # API clients
│   ├── processors/        # Business logic
│   ├── exporters/         # Export formats
│   ├── ui/                # Streamlit pages & components
│   └── utils/             # Utilities
├── tests/                 # Test suite
├── docs/                  # Documentation
├── Dockerfile             # Multi-stage container build
└── Makefile               # Docker commands
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Configuration

### Environment Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `ATLASSIAN_URL` | Your Atlassian instance URL | `https://company.atlassian.net` | Yes |
| `ATLASSIAN_USERNAME` | Your email (for Basic Auth) | `user@company.com` | Yes* |
| `ATLASSIAN_API_TOKEN` | API token | `abc123...` | Yes |
| `ATLASSIAN_PROJECT_KEYS` | Project keys (comma-separated) | `PROJ1,PROJ2` | No (fetches all if empty) |

*Required for Atlassian Cloud Basic Authentication with API tokens

## Testing

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=src

# Specific test
pytest tests/test_config.py -v
```

## Troubleshooting

### "Missing environment variables"
- Check `.env` file exists in project root
- Verify all variables are set
- No spaces around `=`

### "Authentication failed"
- Regenerate API token in Jira
- Verify username is your email (required for Basic Auth)
- Check URL has no trailing slash
- Ensure API token has not expired

### "No data found"
- Verify you logged time in Jira
- Check project keys are correct
- Ensure date range covers your work

## License

MIT License - see LICENSE file

## Support

- **Issues**: GitHub Issues
- **Docs**: Check project documentation

---

**Built with ❤️ for clean, maintainable code**
