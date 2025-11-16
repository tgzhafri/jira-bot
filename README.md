# Automate Jira

> Professional time tracking and reporting tool for Jira

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- 🌐 **Web UI** - Interactive Streamlit interface with one-click report generation
- 🐳 **Docker Ready** - Fully containerized for easy deployment anywhere
- 📊 **CSV Export** - Team overview with hours per person per component
- 👤 **User Filtering** - Generate reports for all users or specific individuals
- 📅 **Monthly Breakdown** - View individual user hours distributed across 12 months
- 📁 **Project Selection** - Filter reports by specific projects
- 📋 **Table Preview** - View reports in proper table format before downloading
- ⚡ **High Performance** - Parallel processing, caching, and optimized API calls (70-90% faster)
- 💾 **Smart Caching** - Instant re-runs with automatic response caching
- 🏗️ **Modular Architecture** - Clean, maintainable code structure
- 🔒 **Type Safe** - Full type hints throughout

## Quick Start

> **New to this?** Check [QUICK_START.md](QUICK_START.md) for a 2-minute setup guide.

### Option 1: Docker (Recommended)

```bash
# Start web UI with one command
make web

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
```

### 2. Configuration

Create `.env` file:

```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your-api-token
# JIRA_PROJECT_KEY=PROJ1,PROJ2  # Optional: leave empty to fetch all projects
```

Get your API token: https://id.atlassian.com/manage-profile/security/api-tokens

**Note**: If `JIRA_PROJECT_KEY` is not set or empty, the tool will automatically fetch all accessible projects.

### 3. Generate Report

```bash
python scripts/generate_report.py
```

Output: `manhour_report_2025.csv`

**Performance**: First run ~20-30s, subsequent runs ~2s (with cache)

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

### Monthly Breakdown (Single User)

```csv
Project,Component,Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec,Total
ERP,HR,5.0,8.0,12.0,10.0,5.0,,,,,,,40.0
ERP,Recruitment,2.0,4.0,6.0,4.0,4.0,2.0,2.0,,,,,24.0
TOTAL,,7.0,12.0,20.0,16.0,9.0,2.0,2.0,,,,,68.0
```

- **One row** per project-component combination
- **One column** per month (Jan-Dec)
- **Total column** showing yearly sum
- **Summary row** with monthly and grand totals

See [docs/FEATURES.md](docs/FEATURES.md) for detailed feature documentation.

## Usage

### Basic

```bash
# Generate current year report (all projects)
python scripts/generate_report.py

# Clear cache (force fresh data)
python scripts/clear_cache.py
```

The script will:
- Fetch all accessible projects (or only specified ones if JIRA_PROJECT_KEY is set)
- Collect worklogs from all team members using parallel processing
- Generate CSV with hours per person per component
- Cache responses for faster subsequent runs

### As Library

```python
from src.config import Config
from src.jira_client import JiraClient
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
├── app.py                 # Web UI entry point
├── src/                   # Core business logic
│   ├── config.py          # Configuration
│   ├── jira_client.py     # API client
│   ├── models.py          # Data models
│   ├── processors/        # Business logic
│   ├── exporters/         # Export formats
│   └── utils/             # Utilities
├── scripts/               # CLI scripts
│   ├── generate_report.py
│   └── clear_cache.py
├── tests/                 # Test suite
├── docs/                  # Documentation
├── Dockerfile             # CLI container
├── Dockerfile.streamlit   # Web UI container
└── Makefile               # Docker commands
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Configuration

### Environment Variables

| Variable | Description | Example | Required |
|----------|-------------|---------|----------|
| `JIRA_URL` | Your Jira instance URL | `https://company.atlassian.net` | Yes |
| `JIRA_USERNAME` | Your email (for Basic Auth) | `user@company.com` | Yes* |
| `JIRA_API_TOKEN` | API token | `abc123...` | Yes |
| `JIRA_PROJECT_KEY` | Project keys (comma-separated) | `PROJ1,PROJ2` | No (fetches all if empty) |
| `JIRA_ENABLE_CACHE` | Enable response caching | `true` | No (default: true) |
| `JIRA_CACHE_DIR` | Cache directory | `.cache` | No (default: .cache) |
| `JIRA_MAX_WORKERS` | Parallel workers | `8` | No (default: 8) |

*Required for Jira Cloud Basic Authentication with API tokens

### Performance Tuning

See [PERFORMANCE.md](PERFORMANCE.md) for detailed optimization guide.

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
- **Email**: support@company.com

---

**Built with ❤️ for clean, maintainable code**
