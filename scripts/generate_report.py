#!/usr/bin/env python3
"""
Main CLI script for generating Jira time tracking reports
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config, ReportConfig, ExportConfig
from src.jira_client import JiraClient, JiraClientError
from src.processors import WorklogProcessor
from src.exporters import TeamOverviewExporter
from src.utils import get_month_range, format_date_for_jql, setup_logging

logger = logging.getLogger(__name__)


def fetch_month_project_data(
    client: JiraClient,
    processor: WorklogProcessor,
    project_key: str,
    year: int,
    month: int,
    filter_author = None
) -> Tuple[str, int, List]:
    """Fetch and process data for a single month-project combination"""
    try:
        start_date, end_date = get_month_range(year, month)
        start_str = format_date_for_jql(start_date)
        end_str = format_date_for_jql(end_date)
        
        # Fetch issues (filtered by user email if specified)
        # Use email for JQL query if author is provided
        filter_user_email = filter_author.email if filter_author and filter_author.email else None
        raw_issues = client.get_issues_with_worklog(
            project_key,
            start_str,
            end_str,
            filter_user=filter_user_email
        )
        
        # Parse issues - fetch all worklogs to get all team members
        issues = [client.parse_issue(raw, fetch_all_worklogs=True) for raw in raw_issues]
        
        # Log unique authors in this batch
        batch_authors = set()
        for issue in issues:
            for worklog in issue.worklogs:
                batch_authors.add(worklog.author.display_name)
        
        if batch_authors:
            logger.debug(f"{project_key} {year}-{month:02d}: {len(batch_authors)} authors - {', '.join(sorted(batch_authors))}")
        
        # Process into time entries (filter by author if specified)
        entries = processor.process_issues(
            issues,
            project_key,
            start_date,
            end_date,
            filter_author=filter_author
        )
        
        logger.info(f"✓ {project_key} {year}-{month:02d}: {len(entries)} entries")
        return (project_key, month, entries)
        
    except JiraClientError as e:
        logger.warning(f"Failed to process {project_key} for {year}-{month:02d}: {e}")
        return (project_key, month, [])


def generate_csv_report(
    config: Config,
    year: int = None,
    output_file: str = None,
    max_workers: int = None,
    filter_author = None,
    monthly_breakdown: bool = False
):
    """Generate CSV team overview report with parallel processing
    
    Args:
        config: Configuration object
        year: Report year
        output_file: Output file path
        max_workers: Number of parallel workers
        filter_author: Author object to filter (for monthly breakdown)
        monthly_breakdown: If True, generate monthly breakdown report for single user
    """
    
    if year is None:
        year = datetime.now().year
    
    if max_workers is None:
        max_workers = config.jira.max_workers
    
    report_type = "monthly breakdown" if monthly_breakdown else "team overview"
    user_info = f" for {filter_author.display_name}" if filter_author else ""
    logger.info(f"Generating CSV {report_type} report for {year}{user_info}")
    
    # Initialize components with cache settings from config
    client = JiraClient(
        config.jira, 
        enable_cache=config.jira.enable_cache,
        cache_dir=config.jira.cache_dir
    )
    processor = WorklogProcessor(config.report)
    
    # Test connection
    if not client.test_connection():
        logger.error("Failed to connect to Jira")
        return None
    
    # Get project keys - fetch all if not specified
    if config.jira.project_keys is None:
        logger.info("No projects specified, fetching all accessible projects...")
        project_keys = client.get_all_projects()
        if not project_keys:
            logger.error("No projects found")
            return None
    else:
        project_keys = config.jira.project_keys
    
    logger.info(f"Projects: {', '.join(project_keys)}")
    logger.info(f"Using parallel processing with {max_workers} workers")
    logger.info(f"Cache: {'enabled' if config.jira.enable_cache else 'disabled'}")
    
    # Start timing
    start_time = time.time()
    
    # Collect all entries for the year using parallel processing
    all_entries = []
    
    # Create tasks for all month-project combinations
    tasks = []
    for month in range(1, 13):
        for project_key in project_keys:
            tasks.append((project_key, year, month))
    
    logger.info(f"Processing {len(tasks)} month-project combinations in parallel...")
    fetch_start = time.time()
    
    # Store entries by month for monthly breakdown
    entries_by_month = {month: [] for month in range(1, 13)} if monthly_breakdown else None
    
    # Execute tasks in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(fetch_month_project_data, client, processor, pk, y, m, filter_author): (pk, m)
            for pk, y, m in tasks
        }
        
        # Collect results as they complete
        completed = 0
        for future in as_completed(future_to_task):
            project_key, month = future_to_task[future]
            completed += 1
            try:
                _, result_month, entries = future.result()
                if monthly_breakdown:
                    entries_by_month[result_month].extend(entries)
                else:
                    all_entries.extend(entries)
                logger.info(f"Progress: {completed}/{len(tasks)} completed")
            except Exception as e:
                logger.error(f"Task failed for {project_key} {year}-{month:02d}: {e}")
    
    fetch_time = time.time() - fetch_start
    logger.info(f"✓ Data fetching completed in {fetch_time:.1f}s")
    
    # Check if we have data
    if monthly_breakdown:
        has_data = any(entries for entries in entries_by_month.values())
    else:
        has_data = bool(all_entries)
    
    if not has_data:
        logger.warning("No data found for the specified period")
        return None
    
    # Export to CSV
    if output_file is None:
        if monthly_breakdown:
            output_file = f"monthly_breakdown_{year}.csv"
        else:
            output_file = f"manhour_report_{year}.csv"
    
    output_path = Path(output_file)
    export_start = time.time()
    
    if monthly_breakdown:
        # Export monthly breakdown report
        from src.exporters.monthly_breakdown_exporter import MonthlyBreakdownExporter
        exporter = MonthlyBreakdownExporter(output_path)
        result_path = exporter.export_monthly_breakdown(
            year=year,
            project_keys=project_keys,
            entries_by_month=entries_by_month,
            processor=processor
        )
        
        # Calculate summary
        total_hours = 0
        for month_entries in entries_by_month.values():
            aggregated_month = processor.aggregate_entries(month_entries)
            total_hours += sum(e.hours for e in aggregated_month.values())
        
        unique_components = set()
        for month_entries in entries_by_month.values():
            for entry in month_entries:
                unique_components.add(entry.project_component)
        
        print(f"\n{'='*60}")
        print(f"  Monthly Breakdown Report Summary")
        print(f"{'='*60}")
        print(f"  Year: {year}")
        print(f"  User: {filter_author.display_name if filter_author else 'Unknown'}")
        print(f"  Projects: {', '.join(project_keys)}")
        print(f"  Total hours: {total_hours:.1f}h")
        print(f"  Components: {len(unique_components)}")
        print(f"  Output: {result_path}")
        print(f"{'='*60}\n")
        
    else:
        # Standard team overview report
        # Aggregate entries
        agg_start = time.time()
        aggregated = processor.aggregate_entries(all_entries)
        agg_time = time.time() - agg_start
        logger.info(f"✓ Data aggregation completed in {agg_time:.1f}s")
        
        # Log unique team members found
        unique_authors_found = set(entry.author for entry in aggregated.values())
        logger.info(f"Found {len(unique_authors_found)} unique team members:")
        for author in sorted(unique_authors_found, key=lambda a: a.display_name):
            logger.info(f"  - {author.display_name} ({author.email})")
        
        # Create yearly report
        from src.models import YearlyReport, MonthlyReport
        yearly_report = YearlyReport(
            year=year,
            project_keys=project_keys,
            monthly_reports=[]
        )
        
        # Manually add entries to a dummy monthly report for export
        dummy_report = MonthlyReport(
            year=year,
            month=1,
            project_keys=project_keys,
            entries=list(aggregated.values())
        )
        yearly_report.monthly_reports = [dummy_report]
        
        exporter = TeamOverviewExporter(output_path)
        result_path = exporter.export_yearly(yearly_report)
        
        # Print summary
        total_hours = sum(e.hours for e in aggregated.values())
        unique_authors = len(set(e.author for e in aggregated.values()))
        unique_components = len(set(e.project_component for e in aggregated.values()))
        
        print(f"\n{'='*60}")
        print(f"  CSV Report Summary")
        print(f"{'='*60}")
        print(f"  Year: {year}")
        print(f"  Projects: {', '.join(project_keys)}")
        print(f"  Total hours: {total_hours:.1f}h")
        print(f"  Team members: {unique_authors}")
        print(f"  Components: {unique_components}")
        print(f"  Output: {result_path}")
        print(f"{'='*60}\n")
    
    export_time = time.time() - export_start
    total_time = time.time() - start_time
    
    logger.info(f"✅ CSV report generated: {result_path}")
    logger.info(f"⏱️  Performance: Fetch={fetch_time:.1f}s, Export={export_time:.1f}s, Total={total_time:.1f}s")
    
    return result_path


def main():
    """Main entry point"""
    
    # Setup logging
    setup_logging(level="INFO", verbose=False)
    
    try:
        # Load configuration
        config = Config.from_env()
        config.validate()
        
        # Generate report
        current_year = datetime.now().year
        generate_csv_report(config, year=current_year)
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except JiraClientError as e:
        logger.error(f"Jira error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
