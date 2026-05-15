"""
Report generation module for Jira time tracking.

Architecture:
    - Data retrieval: Parallel fetch of issues via JQL (time-bounded)
    - Processing: Aggregation of worklogs by person/project/period
    - Export: Formatting and file output via exporters

Performance optimizations:
    - Parallel month×project fetching with ThreadPoolExecutor
    - Batched user-active-status prefetch (eliminates N+1)
    - Performance metrics logging
    - Efficient field filtering in JQL queries
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import Config
from ..exporters import (
    MonthlyBreakdownExporter,
    QuarterlyBreakdownExporter,
    WeeklyBreakdownExporter,
    YearlyOverviewExporter,
)
from ..models import MonthlyReport, YearlyReport
from ..processors import WorklogProcessor
from ..utils import format_date_for_jql, get_month_range
from ..utils.date_utils import MALAYSIA_TZ
from ..utils.performance import PerformanceTracker, timed_operation
from .jira_client import JiraClient, JiraClientError

logger = logging.getLogger(__name__)


class ReportType(Enum):
    """Enum for report types."""
    YEARLY = "Yearly Overview"
    QUARTERLY = "Quarterly Breakdown"
    MONTHLY = "Monthly Breakdown"
    WEEKLY = "Weekly Breakdown"


class ReportConfig:
    """Configuration for report generation."""

    EXPORTER_MAP = {
        ReportType.YEARLY: YearlyOverviewExporter,
        ReportType.QUARTERLY: QuarterlyBreakdownExporter,
        ReportType.MONTHLY: MonthlyBreakdownExporter,
        ReportType.WEEKLY: WeeklyBreakdownExporter,
    }

    DEFAULT_FILENAMES = {
        ReportType.YEARLY: "manhour_report_{year}.csv",
        ReportType.QUARTERLY: "quarterly_report_{year}.csv",
        ReportType.MONTHLY: "monthly_breakdown_{year}.csv",
        ReportType.WEEKLY: "weekly_breakdown_{year}.csv",
    }

    @classmethod
    def get_exporter_class(cls, report_type: ReportType):
        """Get exporter class for report type."""
        return cls.EXPORTER_MAP[report_type]

    @classmethod
    def get_default_filename(cls, report_type: ReportType, year: int) -> str:
        """Get default filename for report type."""
        return cls.DEFAULT_FILENAMES[report_type].format(year=year)


# ─── Data Retrieval Layer ──────────────────────────────────────────────


def fetch_month_project_data(
    client: JiraClient,
    processor: WorklogProcessor,
    project_key: str,
    year: int,
    month: int,
    filter_author=None,
) -> Tuple[str, int, List]:
    """Fetch and process data for a single month-project combination.

    This is the atomic unit of work for parallel fetching.

    Args:
        client: JiraClient instance (shared, thread-safe via Session).
        processor: WorklogProcessor for aggregation.
        project_key: Jira project key.
        year: Report year.
        month: Report month (1-12).
        filter_author: Optional Author to filter worklogs.

    Returns:
        Tuple of (project_key, month, time_entries).
    """
    try:
        start_date, end_date = get_month_range(year, month)
        start_str = format_date_for_jql(start_date)
        end_str = format_date_for_jql(end_date)

        # Fetch issues (filtered by user email if specified)
        filter_user_email = (
            filter_author.email if filter_author and filter_author.email else None
        )
        raw_issues = client.get_issues_with_worklog(
            project_key, start_str, end_str, filter_user=filter_user_email
        )

        # Prefetch author active status to eliminate N+1 queries
        client.prefetch_authors_from_issues(raw_issues)

        # Parse issues
        issues = [client.parse_issue(raw, fetch_all_worklogs=True) for raw in raw_issues]

        # Process into time entries
        entries = processor.process_issues(
            issues, project_key, start_date, end_date, filter_author=filter_author
        )

        logger.info(
            "✓ %s %d-%02d: %d entries from %d issues",
            project_key, year, month, len(entries), len(issues),
        )
        return (project_key, month, entries)

    except JiraClientError as e:
        logger.warning(
            "Failed to process %s for %d-%02d: %s", project_key, year, month, e
        )
        return (project_key, month, [])


def _fetch_data_parallel(
    client: JiraClient,
    processor: WorklogProcessor,
    project_keys: List[str],
    year: int,
    max_workers: int,
    preserve_months: bool = False,
) -> dict:
    """Fetch data in parallel for all month-project combinations.

    Args:
        client: JiraClient instance.
        processor: WorklogProcessor instance.
        project_keys: List of project keys to fetch.
        year: Report year.
        max_workers: Number of parallel workers.
        preserve_months: If True, returns dict with month keys.
            If False, returns flat list.

    Returns:
        Either dict[month -> entries] or flat list of entries.
    """
    # Create tasks for all month-project combinations
    tasks = []
    for month in range(1, 13):
        for project_key in project_keys:
            tasks.append((project_key, year, month))

    logger.info(
        "Processing %d month-project combinations with %d workers...",
        len(tasks), max_workers,
    )

    with timed_operation("Data fetching ({} tasks)".format(len(tasks))):
        # Store entries by month if needed
        if preserve_months:
            entries_by_month = {month: [] for month in range(1, 13)}
        else:
            all_entries = []

        # Execute tasks in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(
                    fetch_month_project_data, client, processor, pk, y, m, None
                ): (pk, m)
                for pk, y, m in tasks
            }

            completed = 0
            for future in as_completed(future_to_task):
                project_key, month = future_to_task[future]
                completed += 1
                try:
                    _, result_month, entries = future.result()
                    if preserve_months:
                        entries_by_month[result_month].extend(entries)
                    else:
                        all_entries.extend(entries)
                except Exception as e:
                    logger.error(
                        "Task failed for %s %d-%02d: %s",
                        project_key, year, month, e,
                    )

                # Log progress every 10%
                if completed % max(1, len(tasks) // 10) == 0:
                    logger.info("Progress: %d/%d completed", completed, len(tasks))

    return entries_by_month if preserve_months else all_entries


# ─── Initialization ───────────────────────────────────────────────────


def _initialize_client_and_processor(config: Config):
    """Initialize Jira client and worklog processor."""
    client = JiraClient(
        config.atlassian,
        enable_cache=config.atlassian.enable_cache,
        cache_dir=config.atlassian.cache_dir,
    )
    processor = WorklogProcessor(config.report)

    # Test connection
    if not client.test_connection():
        logger.error("Failed to connect to Jira")
        return None, None

    return client, processor


def _get_project_keys(config: Config, client: JiraClient) -> Optional[List[str]]:
    """Get project keys from config or fetch all accessible projects."""
    if config.atlassian.project_keys is None:
        logger.info("No projects specified, fetching all accessible projects...")
        project_keys = client.get_all_projects()
        if not project_keys:
            logger.error("No projects found")
            return None
    else:
        project_keys = config.atlassian.project_keys

    logger.info("Projects: %s", ", ".join(project_keys))
    return project_keys


# ─── Report Assembly ──────────────────────────────────────────────────


def _create_yearly_report_from_entries(
    entries_data,
    year: int,
    project_keys: List[str],
    preserve_months: bool = False,
) -> YearlyReport:
    """Create YearlyReport object from entries data.

    Args:
        entries_data: Either a list of entries or dict of month->entries.
        year: Report year.
        project_keys: List of project keys.
        preserve_months: Whether entries_data is organized by month.

    Returns:
        YearlyReport instance.
    """
    if preserve_months:
        monthly_reports = []
        for month in range(1, 13):
            monthly_report = MonthlyReport(
                year=year,
                month=month,
                project_keys=project_keys,
                entries=entries_data[month],
            )
            monthly_reports.append(monthly_report)
    else:
        dummy_report = MonthlyReport(
            year=year,
            month=1,
            project_keys=project_keys,
            entries=entries_data,
        )
        monthly_reports = [dummy_report]

    return YearlyReport(
        year=year,
        project_keys=project_keys,
        monthly_reports=monthly_reports,
    )


def _process_yearly_data(processor: WorklogProcessor, entries_data: List) -> List:
    """Aggregate entries for yearly report."""
    with timed_operation("Data aggregation"):
        aggregated = processor.aggregate_entries(entries_data)

    # Log unique team members
    unique_authors = set(entry.author for entry in aggregated.values())
    logger.info("Found %d unique team members:", len(unique_authors))
    for author in sorted(unique_authors, key=lambda a: a.display_name):
        logger.info("  - %s (%s)", author.display_name, author.email)

    return list(aggregated.values())


# ─── Main Report Generation ───────────────────────────────────────────


def generate_report(
    config: Config,
    report_type: ReportType,
    year: int = None,
    output_file: str = None,
    max_workers: int = None,
):
    """Unified report generation function.

    Orchestrates the full pipeline:
    1. Initialize client + processor
    2. Resolve project keys
    3. Fetch data in parallel (month × project)
    4. Aggregate and export

    Args:
        config: Configuration object.
        report_type: Type of report to generate.
        year: Report year (defaults to current year).
        output_file: Output file path (defaults to standard naming).
        max_workers: Number of parallel workers (defaults to config value).

    Returns:
        For yearly reports: Path to CSV file.
        For other reports: Tuple of (csv_path, xlsx_path).
    """
    # Set defaults
    if year is None:
        year = datetime.now().year
    if max_workers is None:
        max_workers = config.atlassian.max_workers
    if output_file is None:
        output_file = "reports/{}".format(
            ReportConfig.get_default_filename(report_type, year)
        )

    logger.info("Generating %s report for %d", report_type.value, year)

    # Initialize components
    client, processor = _initialize_client_and_processor(config)
    if not client or not processor:
        return None

    # Get project keys
    project_keys = _get_project_keys(config, client)
    if not project_keys:
        return None

    logger.info("Using parallel processing with %d workers", max_workers)
    logger.info(
        "Cache: %s", "enabled" if config.atlassian.enable_cache else "disabled"
    )

    # Start timing
    start_time = time.time()

    # Fetch data - preserve months for all except yearly overview
    preserve_months = report_type != ReportType.YEARLY
    entries_data = _fetch_data_parallel(
        client, processor, project_keys, year, max_workers, preserve_months
    )

    # Check if we have data
    if preserve_months:
        has_data = any(entries_data.values())
    else:
        has_data = bool(entries_data)

    if not has_data:
        logger.warning("No data found for the specified period")
        return None

    # Export report
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # For yearly overview, aggregate entries first
    if report_type == ReportType.YEARLY:
        entries_data = _process_yearly_data(processor, entries_data)

    # Create yearly report with timestamp metadata
    yearly_report = _create_yearly_report_from_entries(
        entries_data, year, project_keys, preserve_months
    )

    # Add timestamp metadata (Malaysia time)
    yearly_report.fetch_timestamp = datetime.now(MALAYSIA_TZ)
    yearly_report.from_cache = client.is_using_cache()
    yearly_report.cache_timestamp = client.get_cache_timestamp()

    # Export using appropriate exporter
    with timed_operation("Report export"):
        exporter_class = ReportConfig.get_exporter_class(report_type)
        exporter = exporter_class(output_path, filter_active_only=True)
        result = exporter.export_yearly(yearly_report)

    total_time = time.time() - start_time

    # Log results
    if report_type == ReportType.YEARLY:
        logger.info("✅ CSV report generated: %s", result)
    else:
        csv_path, xlsx_path = result
        logger.info("✅ Reports generated:")
        logger.info("   CSV: %s", csv_path)
        if xlsx_path:
            logger.info("   XLSX: %s", xlsx_path)

    logger.info("⏱️  Total time: %.1fs", total_time)

    # Log performance summary
    client.perf.stats.log_summary("Report Generation")

    return result


# ─── Convenience Functions (backward compatibility) ────────────────────


def generate_csv_report(
    config: Config, year: int = None, output_file: str = None, max_workers: int = None
):
    """Generate CSV team overview report."""
    return generate_report(config, ReportType.YEARLY, year, output_file, max_workers)


def generate_quarterly_report(
    config: Config, year: int = None, output_file: str = None, max_workers: int = None
):
    """Generate CSV quarterly breakdown report."""
    return generate_report(config, ReportType.QUARTERLY, year, output_file, max_workers)


def generate_monthly_breakdown_report(
    config: Config, year: int = None, output_file: str = None, max_workers: int = None
):
    """Generate CSV monthly breakdown report."""
    return generate_report(config, ReportType.MONTHLY, year, output_file, max_workers)


def generate_weekly_breakdown_report(
    config: Config, year: int = None, output_file: str = None, max_workers: int = None
):
    """Generate CSV weekly breakdown report."""
    return generate_report(config, ReportType.WEEKLY, year, output_file, max_workers)
