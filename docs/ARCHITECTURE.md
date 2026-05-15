# Architecture — Atlassian Bot

## Project Structure

```
automate-jira/
├── app.py                      # Streamlit web UI (entry point)
├── src/                        # Core business logic
│   ├── config.py               # Configuration management
│   ├── models/                 # Domain models (dataclasses, enums)
│   ├── services/               # External API clients
│   │   ├── jira_client.py
│   │   ├── worklog_service.py
│   │   ├── jira_backup_service.py
│   │   ├── confluence_client.py
│   │   └── confluence_backup_service.py
│   ├── processors/             # Data transformation
│   │   └── worklog_processor.py
│   ├── exporters/              # Report output formats
│   │   ├── base_exporter.py
│   │   ├── yearly_overview_exporter.py
│   │   ├── quarterly_breakdown_exporter.py
│   │   ├── monthly_breakdown_exporter.py
│   │   └── weekly_breakdown_exporter.py
│   ├── ui/                     # Streamlit UI layer
│   │   ├── state_manager.py
│   │   ├── formatters.py
│   │   ├── report_view.py
│   │   ├── components/
│   │   └── pages/
│   └── utils/                  # Cross-cutting utilities
│       ├── date_utils.py
│       └── logging_config.py
├── tests/                      # Test suite
├── docs/                       # Documentation
├── reports/                    # Generated reports (gitignored)
├── .cache/                     # API cache (gitignored)
├── Dockerfile                  # Multi-stage container build
├── docker-compose.yml          # Service orchestration
├── docker-compose.override.yml # Dev overrides (live reload)
└── Makefile                    # Convenience commands
```

## Design Decisions

### 1. app.py Location (Root Level)

**Why at root:**
- Entry point for Streamlit — conventional location
- Thin UI shell — all business logic lives in `src/`
- Easy to find and run: `streamlit run app.py`
- Dockerfile references it directly

**Why NOT in src/:**
- `src/` is for reusable business logic
- `app.py` is application-specific, not a library
- Would complicate imports and Docker setup

### 2. Web-Only Interface

The application is accessed exclusively through the Streamlit web UI. This simplifies deployment (single container, single entry point) and provides a richer experience with interactive filters, table previews, and direct downloads.

### 3. Separation of Concerns

**Layer 1: UI (`app.py` + `src/ui/`)**
- Streamlit interface
- User input handling
- Display logic
- Page routing

**Layer 2: Business Logic (`src/`)**
- Services: API communication and caching
- Processors: Data aggregation and transformation
- Exporters: Report formatting and file output
- Models: Domain types

**Layer 3: Infrastructure (Docker, Makefile)**
- Containerization
- Deployment
- Development tools

## Data Flow

```
User Input (app.py → src/ui/pages/)
    ↓
Configuration (src/config.py)
    ↓
Services (src/services/jira_client.py, worklog_service.py)
    ↓
API Requests → Cache → Response
    ↓
Processors (src/processors/worklog_processor.py)
    ↓
Exporters (src/exporters/*_exporter.py)
    ↓
File Output (reports/) → Display in UI
```

## Key Components

### app.py
**Purpose:** Web UI entry point (thin shell)
**Responsibilities:**
- Streamlit page configuration
- Sidebar navigation
- Page routing
- Global footer

### src/ui/pages/
**Purpose:** Individual page modules
**Responsibilities:**
- User input collection
- Progress indication
- Report preview display
- Download functionality

### src/services/
**Purpose:** External API abstraction
**Responsibilities:**
- Authentication
- API requests with caching
- Parallel data fetching
- Error handling

### src/processors/
**Purpose:** Data transformation
**Responsibilities:**
- Worklog parsing and aggregation
- Time period calculations
- Work type classification

### src/exporters/
**Purpose:** Report output
**Responsibilities:**
- CSV/XLSX generation
- Multi-level headers
- Metadata headers with timestamps

## Performance Optimizations

1. **Parallel Processing**
   - ThreadPoolExecutor for concurrent API calls
   - Configurable worker count (default: 8)

2. **Smart Caching**
   - requests-cache for transparent API response caching
   - Persistent cache directory
   - Configurable enable/disable

3. **Efficient Data Structures**
   - Pandas for data manipulation
   - Dataclasses for domain models
   - Minimal memory footprint

## Testing Strategy

```
tests/
├── test_config.py          # Configuration tests
├── test_jira_client.py     # API client tests
├── test_processors.py      # Business logic tests
├── test_exporters.py       # Export format tests
├── test_integration.py     # End-to-end tests
└── test_benchmark.py       # Performance tests
```

## Deployment

Single Docker container running Streamlit:

```bash
make up    # → http://localhost:8501
```

For production, remove `docker-compose.override.yml` (disables source mounts) and deploy the image to any container platform (ECS, Cloud Run, Render, etc.).

## Future Considerations

### If adding more features:
1. Plugin architecture for exporters
2. Additional report types (subclass `BaseExporter`)
3. Scheduled report generation
4. Email delivery

### If scaling:
1. Redis for distributed caching
2. Queue system for async processing
3. Database for report history
4. API layer for programmatic access

## Best Practices

1. **Keep app.py thin** — routing only, no business logic
2. **Business logic in src/** — reusable and testable
3. **Type hints everywhere** — better IDE support and validation
4. **Comprehensive tests** — confidence in changes
5. **Docker-first** — consistent deployments

---

**Last Updated:** 2026-05-15
**Version:** 2.1.0
