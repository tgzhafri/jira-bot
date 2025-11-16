# Architecture - Automate Jira

## Project Structure

```
automate-jira/
├── app.py                      # Streamlit web UI (entry point)
├── scripts/
│   ├── generate_report.py      # CLI report generation
│   └── clear_cache.py          # Cache management
├── src/                        # Core business logic
│   ├── config.py               # Configuration management
│   ├── jira_client.py          # Jira API client
│   ├── models.py               # Data models
│   ├── processors/             # Business logic
│   │   └── worklog_processor.py
│   ├── exporters/              # Export formats
│   │   └── csv_exporter.py
│   └── utils/                  # Utilities
│       ├── date_utils.py
│       └── logging_utils.py
├── tests/                      # Test suite
├── docs/                       # Documentation
├── reports/                    # Generated reports (gitignored)
├── .cache/                     # API cache (gitignored)
├── Dockerfile                  # CLI container
├── Dockerfile.streamlit        # Web UI container
├── docker-compose.yml          # CLI orchestration
├── docker-compose.streamlit.yml # Web UI orchestration
└── Makefile                    # Convenience commands
```

## Design Decisions

### 1. app.py Location (Root Level)

**Why at root:**
- Entry point for Streamlit - conventional location
- Thin UI layer - doesn't contain business logic
- Easy to find and run: `streamlit run app.py`
- Dockerfile references it directly
- Separation of concerns: UI vs business logic

**Why NOT in src/:**
- src/ is for reusable business logic
- app.py is application-specific, not a library
- Would complicate imports and Docker setup

### 2. Monolithic vs Modular app.py

**Current approach: Monolithic with helper functions**

**Rationale:**
- Simple UI with ~250 lines - manageable size
- Helper functions provide structure without over-engineering
- Business logic already separated in `scripts/` and `src/`
- Easy to understand for contributors
- No need for complex UI framework

**If it grows beyond 500 lines, consider:**
```
src/ui/
├── __init__.py
├── components.py      # Reusable UI components
├── config_panel.py    # Sidebar configuration
└── report_display.py  # Report preview logic
```

### 3. Separation of Concerns

**Layer 1: UI (app.py)**
- Streamlit interface
- User input handling
- Display logic
- Thin wrapper around business logic

**Layer 2: Application Logic (scripts/)**
- CLI entry points
- Report generation orchestration
- High-level workflows

**Layer 3: Business Logic (src/)**
- Jira API client
- Data processing
- Export formats
- Reusable components

**Layer 4: Infrastructure (Docker, Makefile)**
- Containerization
- Deployment
- Development tools

## Data Flow

```
User Input (app.py)
    ↓
Configuration (src/config.py)
    ↓
Report Generation (scripts/generate_report.py)
    ↓
Jira Client (src/jira_client.py)
    ↓
API Requests → Cache → Response
    ↓
Worklog Processor (src/processors/)
    ↓
CSV Exporter (src/exporters/)
    ↓
File Output → Display (app.py)
```

## Key Components

### app.py
**Purpose:** Web UI entry point
**Responsibilities:**
- Streamlit page configuration
- User input collection
- Progress indication
- Report preview display
- Download functionality

**Functions:**
- `main()` - Application entry point
- `show_config_error()` - Error display
- `calculate_summary_stats()` - Metrics calculation
- `display_report_preview()` - Table rendering

### scripts/generate_report.py
**Purpose:** Report generation orchestration
**Responsibilities:**
- CLI interface
- Parallel data fetching
- Progress logging
- Report aggregation

### src/jira_client.py
**Purpose:** Jira API abstraction
**Responsibilities:**
- Authentication
- API requests
- Response caching
- Error handling

### src/processors/worklog_processor.py
**Purpose:** Business logic
**Responsibilities:**
- Worklog parsing
- Time aggregation
- Data transformation

### src/exporters/csv_exporter.py
**Purpose:** Output formatting
**Responsibilities:**
- CSV generation
- File writing
- Format validation

## Performance Optimizations

1. **Parallel Processing**
   - ThreadPoolExecutor for concurrent API calls
   - Configurable worker count (default: 8)

2. **Smart Caching**
   - requests-cache for API responses
   - Persistent cache directory
   - Configurable enable/disable

3. **Efficient Data Structures**
   - Pandas for data manipulation
   - Type hints for optimization
   - Minimal memory footprint

## Testing Strategy

```
tests/
├── test_config.py          # Configuration tests
├── test_jira_client.py     # API client tests
├── test_processors.py      # Business logic tests
├── test_exporters.py       # Export format tests
├── test_integration.py     # End-to-end tests
├── test_setup.py           # Setup verification
└── test_benchmark.py       # Performance tests
```

## Deployment Options

### 1. Docker (Recommended)
- Consistent environment
- Easy deployment
- Isolated dependencies

### 2. Local Python
- Development
- Quick testing
- Custom environments

### 3. Cloud Platforms
- Render/Railway (free tier)
- AWS ECS/Fargate
- Google Cloud Run
- Kubernetes

## Future Considerations

### If app.py grows large:
1. Extract UI components to `src/ui/`
2. Create page modules for multi-page app
3. Add state management layer

### If adding more features:
1. Plugin architecture for exporters
2. Multiple report types
3. Scheduled report generation
4. Email delivery

### If scaling:
1. Redis for distributed caching
2. Queue system for async processing
3. Database for report history
4. API layer for programmatic access

## Best Practices

1. **Keep app.py thin** - UI logic only
2. **Business logic in src/** - Reusable and testable
3. **Scripts for workflows** - High-level orchestration
4. **Type hints everywhere** - Better IDE support and validation
5. **Comprehensive tests** - Confidence in changes
6. **Docker-first** - Consistent deployments

---

**Last Updated:** 2025-11-13
**Version:** 2.1.0
