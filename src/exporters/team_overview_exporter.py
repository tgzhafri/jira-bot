"""
Team overview CSV exporter for multi-user reports
"""

import csv
import logging
from pathlib import Path
from collections import defaultdict

from .base_exporter import BaseExporter
from ..models import YearlyReport, MonthlyReport, ProjectComponent

logger = logging.getLogger(__name__)


class TeamOverviewExporter(BaseExporter):
    """Export team overview reports to CSV format"""
    
    def __init__(self, output_path: Path, filter_active_only: bool = True):
        """Initialize exporter with option to filter active employees only"""
        super().__init__(output_path)
        self.filter_active_only = filter_active_only
    
    def export_yearly(self, report: YearlyReport) -> Path:
        """Export yearly report to CSV with separate sections for Development and Maintenance"""
        
        self._ensure_directory()
        
        # Aggregate data across all months
        # Structure: {WorkType: {ProjectComponent: {Author: hours}}}
        from ..models import WorkType
        
        data_by_type = {
            WorkType.DEVELOPMENT: defaultdict(lambda: defaultdict(float)),
            WorkType.MAINTENANCE: defaultdict(lambda: defaultdict(float))
        }
        all_authors = set()
        
        # Track all authors encountered for debugging
        all_encountered_authors = set()
        filtered_authors = set()
        
        for monthly_report in report.monthly_reports:
            for entry in monthly_report.entries:
                pc = entry.project_component
                author = entry.author
                work_type = entry.work_type
                
                # Track all authors we encounter
                all_encountered_authors.add(author)
                
                # Filter by active status if specified
                if self.filter_active_only and not author.active:
                    filtered_authors.add(author)
                    logger.info(f"FILTERED OUT: {author.display_name} (email={author.email}, active={author.active})")
                    continue
                
                # Only track Development and Maintenance
                if work_type in [WorkType.DEVELOPMENT, WorkType.MAINTENANCE]:
                    data_by_type[work_type][pc][author] += entry.hours
                    all_authors.add(author)
                    logger.debug(f"INCLUDED: {author.display_name} (email={author.email}, active={author.active})")
        
        # Log summary
        logger.info(f"Total authors encountered: {len(all_encountered_authors)}")
        logger.info(f"Inactive authors filtered out: {len(filtered_authors)}")
        logger.info(f"Active authors included in report: {len(all_authors)}")
        
        # Sort authors by display name
        sorted_authors = sorted(all_authors, key=lambda a: a.display_name)
        
        # Write CSV with separate sections
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header row - format names in Title Case
            header = ['Project', 'Component'] + [a.display_name.title() for a in sorted_authors]
            
            # Write Development section
            writer.writerow(['DEVELOPMENT'])
            writer.writerow(header)
            
            dev_data = data_by_type[WorkType.DEVELOPMENT]
            sorted_dev_pcs = sorted(dev_data.keys(), key=lambda pc: (pc.project, pc.component.name))
            
            for pc in sorted_dev_pcs:
                row = [pc.project, pc.component.name]
                for author in sorted_authors:
                    hours = dev_data[pc].get(author, 0)
                    row.append(f"{hours:.1f}" if hours > 0 else "")
                writer.writerow(row)
            
            # Development total row
            dev_total_row = ['TOTAL', '']
            for author in sorted_authors:
                total_hours = sum(dev_data[pc].get(author, 0) for pc in sorted_dev_pcs)
                dev_total_row.append(f"{total_hours:.1f}" if total_hours > 0 else "")
            writer.writerow(dev_total_row)
            
            # Empty row separator
            writer.writerow([])
            
            # Write Maintenance section
            writer.writerow(['MAINTENANCE'])
            writer.writerow(header)
            
            maint_data = data_by_type[WorkType.MAINTENANCE]
            sorted_maint_pcs = sorted(maint_data.keys(), key=lambda pc: (pc.project, pc.component.name))
            
            for pc in sorted_maint_pcs:
                row = [pc.project, pc.component.name]
                for author in sorted_authors:
                    hours = maint_data[pc].get(author, 0)
                    row.append(f"{hours:.1f}" if hours > 0 else "")
                writer.writerow(row)
            
            # Maintenance total row
            maint_total_row = ['TOTAL', '']
            for author in sorted_authors:
                total_hours = sum(maint_data[pc].get(author, 0) for pc in sorted_maint_pcs)
                maint_total_row.append(f"{total_hours:.1f}" if total_hours > 0 else "")
            writer.writerow(maint_total_row)
        
        logger.info(f"CSV report exported to {self.output_path}")
        logger.info(f"  Development rows: {len(sorted_dev_pcs)}, Maintenance rows: {len(sorted_maint_pcs)}")
        logger.info(f"  Team members: {len(sorted_authors)}")
        
        return self.output_path
    
    def export_monthly(self, report: MonthlyReport) -> Path:
        """Export monthly report to CSV"""
        
        self._ensure_directory()
        
        # Aggregate data for the month
        data = defaultdict(lambda: defaultdict(float))
        all_authors = set()
        
        for entry in report.entries:
            pc = entry.project_component
            author = entry.author
            data[pc][author] += entry.hours
            all_authors.add(author)
        
        # Sort authors
        sorted_authors = sorted(all_authors, key=lambda a: a.display_name)
        
        # Write CSV
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            header = ['Project', 'Component'] + [a.display_name for a in sorted_authors]
            writer.writerow(header)
            
            # Data rows
            sorted_pcs = sorted(data.keys(), key=lambda pc: (pc.project, pc.component.name))
            
            for pc in sorted_pcs:
                row = [pc.project, pc.component.name]
                for author in sorted_authors:
                    hours = data[pc].get(author, 0)
                    row.append(f"{hours:.1f}" if hours > 0 else "")
                writer.writerow(row)
            
            # Add total row
            writer.writerow([])  # Empty row for separation
            total_row = ['TOTAL', '']
            for author in sorted_authors:
                total_hours = sum(data[pc].get(author, 0) for pc in sorted_pcs)
                total_row.append(f"{total_hours:.1f}" if total_hours > 0 else "")
            writer.writerow(total_row)
        
        logger.info(f"CSV report exported to {self.output_path}")
        
        return self.output_path
