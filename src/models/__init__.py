"""
Data models for Automate Jira and Confluence backup operations.

Re-exports all models from the original Jira models module and the new
Confluence backup models module for backward compatibility.
"""

# Re-export all original Jira models for backward compatibility
from ._models import (
    Author,
    Component,
    Issue,
    MonthlyReport,
    ProjectComponent,
    TimeEntry,
    WorkType,
    Worklog,
    YearlyReport,
)

# Export Confluence backup models
from .confluence_models import (
    ConfluenceJobDetails,
    ConfluenceJobOperation,
    ConfluenceJobScope,
    ConfluenceJobState,
    ConfluenceStatistics,
    parse_job_details,
)

__all__ = [
    # Jira models
    "Author",
    "Component",
    "Issue",
    "MonthlyReport",
    "ProjectComponent",
    "TimeEntry",
    "WorkType",
    "Worklog",
    "YearlyReport",
    # Confluence models
    "ConfluenceJobState",
    "ConfluenceJobOperation",
    "ConfluenceJobScope",
    "ConfluenceStatistics",
    "ConfluenceJobDetails",
    "parse_job_details",
]
