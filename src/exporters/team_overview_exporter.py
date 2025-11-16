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
    
    def export_yearly(self, report: YearlyReport) -> Path:
        """Export yearly report to CSV"""
        
        self._ensure_directory()
        
        # Aggregate data across all months
        # Structure: {ProjectComponent: {Author: hours}}
        data = defaultdict(lambda: defaultdict(float))
        all_authors = set()
        
        for monthly_report in report.monthly_reports:
            for entry in monthly_report.entries:
                pc = entry.project_component
                author = entry.author
                data[pc][author] += entry.hours
                all_authors.add(author)
        
        # Sort authors by display name
        sorted_authors = sorted(all_authors, key=lambda a: a.display_name)
        
        # Write CSV
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header
            header = ['Project', 'Component'] + [a.display_name for a in sorted_authors]
            writer.writerow(header)
            
            # Data rows - sorted by project then component
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
        logger.info(f"  Rows: {len(data)}, Team members: {len(sorted_authors)}")
        
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
