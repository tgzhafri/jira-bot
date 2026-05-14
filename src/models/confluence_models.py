"""
Data models for Confluence Data Center backup and restore operations.

Defines enums for job state, operation, and scope; dataclasses for job details
and statistics; and a parsing function for converting API JSON responses into
typed Python objects.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class ConfluenceJobState(Enum):
    """Job lifecycle states for Confluence backup/restore operations."""

    QUEUED = "QUEUED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ConfluenceJobOperation(Enum):
    """Types of Confluence backup/restore operations."""

    BACKUP = "BACKUP"
    RESTORE = "RESTORE"


class ConfluenceJobScope(Enum):
    """Scope of a Confluence backup/restore job."""

    SITE = "SITE"
    SPACE = "SPACE"


@dataclass
class ConfluenceStatistics:
    """Progress statistics for a Confluence backup/restore job.

    All count fields must be non-negative integers.
    """

    total_objects_count: int = 0
    processed_objects_count: int = 0
    persisted_objects_count: int = 0
    skipped_objects_count: int = 0
    reused_objects_count: int = 0

    def __post_init__(self):
        for field_name in [
            "total_objects_count",
            "processed_objects_count",
            "persisted_objects_count",
            "skipped_objects_count",
            "reused_objects_count",
        ]:
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be >= 0")


@dataclass
class ConfluenceJobDetails:
    """Full details of a Confluence backup/restore job.

    Represents the structured response from the Confluence Data Center
    Backup and Restore REST API.
    """

    id: str
    job_operation: ConfluenceJobOperation
    job_scope: ConfluenceJobScope
    job_state: ConfluenceJobState
    create_time: Optional[datetime] = None
    start_processing_time: Optional[datetime] = None
    finish_processing_time: Optional[datetime] = None
    cancel_time: Optional[datetime] = None
    error_message: Optional[str] = None
    owner: Optional[str] = None
    cancelled_by: Optional[str] = None
    file_name: Optional[str] = None
    space_keys: List[str] = field(default_factory=list)
    file_delete_time: Optional[datetime] = None
    file_exists: bool = True
    statistics: Optional[ConfluenceStatistics] = None

    @property
    def is_terminal(self) -> bool:
        """Whether the job has reached a terminal (final) state."""
        return self.job_state in (
            ConfluenceJobState.COMPLETED,
            ConfluenceJobState.FAILED,
            ConfluenceJobState.CANCELLED,
        )

    @property
    def progress_percent(self) -> Optional[float]:
        """Fraction of objects processed (0.0 to 1.0), or None if unavailable."""
        if self.statistics and self.statistics.total_objects_count > 0:
            return (
                self.statistics.processed_objects_count
                / self.statistics.total_objects_count
            )
        return None


def _parse_timestamp(value, field_name: str) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp string into a datetime object.

    Args:
        value: The raw value from the API response (str, None, or absent).
        field_name: Name of the field, used in error messages.

    Returns:
        A datetime object, or None if the value is None/absent.

    Raises:
        ValueError: If the value is a non-null string that cannot be parsed
            as ISO 8601.
    """
    if value is None:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as e:
        raise ValueError(
            f"Failed to parse timestamp for field '{field_name}': {value!r}"
        ) from e


def _parse_statistics(data: Optional[dict]) -> Optional[ConfluenceStatistics]:
    """Parse a nested statistics object from the API response.

    Args:
        data: The statistics dict from the API, or None.

    Returns:
        A ConfluenceStatistics instance, or None if data is None.
    """
    if data is None:
        return None

    return ConfluenceStatistics(
        total_objects_count=data.get("totalObjectsCount", 0),
        processed_objects_count=data.get("processedObjectsCount", 0),
        persisted_objects_count=data.get("persistedObjectsCount", 0),
        skipped_objects_count=data.get("skippedObjectsCount", 0),
        reused_objects_count=data.get("reusedObjectsCount", 0),
    )


def parse_job_details(data: dict) -> ConfluenceJobDetails:
    """Parse an API JSON response into a ConfluenceJobDetails dataclass.

    Handles:
    - Enum conversion from string values
    - ISO 8601 timestamp parsing (None for absent/null fields)
    - Nested Statistics object parsing
    - spaceKeys list extraction (default empty list)

    Args:
        data: Dictionary from the Confluence API JSON response.

    Returns:
        A fully populated ConfluenceJobDetails instance.

    Raises:
        ValueError: If timestamp fields contain invalid ISO 8601 strings,
            indicating which field failed to parse.
        KeyError: If required fields (id, jobOperation, jobScope, jobState)
            are missing.
    """
    return ConfluenceJobDetails(
        id=data["id"],
        job_operation=ConfluenceJobOperation(data["jobOperation"]),
        job_scope=ConfluenceJobScope(data["jobScope"]),
        job_state=ConfluenceJobState(data["jobState"]),
        create_time=_parse_timestamp(data.get("createTime"), "createTime"),
        start_processing_time=_parse_timestamp(
            data.get("startProcessingTime"), "startProcessingTime"
        ),
        finish_processing_time=_parse_timestamp(
            data.get("finishProcessingTime"), "finishProcessingTime"
        ),
        cancel_time=_parse_timestamp(data.get("cancelTime"), "cancelTime"),
        error_message=data.get("errorMessage"),
        owner=data.get("owner"),
        cancelled_by=data.get("cancelledBy"),
        file_name=data.get("fileName"),
        space_keys=data.get("spaceKeys", []),
        file_delete_time=_parse_timestamp(
            data.get("fileDeleteTime"), "fileDeleteTime"
        ),
        file_exists=data.get("fileExists", True),
        statistics=_parse_statistics(data.get("statistics")),
    )
