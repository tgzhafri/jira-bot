"""
Quarterly breakdown CSV exporter
"""

import csv
import logging
from pathlib import Path
from collections import defaultdict

from .base_exporter import BaseExporter
from ..models import YearlyReport, WorkType

logger = logging.getLogger(__name__)


class QuarterlyBreakdownExporter(BaseExporter):
    """Export quarterly breakdown reports to CSV format"""
    
    def __init__(self, output_path: Path, filter_active_only: bool = True):
        """Initialize exporter with option to filter active employees only"""
        super().__init__(output_path)
        self.filter_active_only = filter_active_only
    
    def _get_quarter(self, month: int) -> int:
        """Get quarter number (1-4) from month (1-12)"""
        return (month - 1) // 3 + 1
    
    def export_yearly(self, report: YearlyReport) -> Path:
        """Export yearly report to CSV with quarterly breakdown by project-component and author"""
        
        self._ensure_directory()
        
        # Aggregate data by quarter and author
        # Structure: {WorkType: {ProjectComponent: {Author: {quarter: hours}}}}
        from ..models import WorkType
        
        data_by_type = {
            WorkType.DEVELOPMENT: defaultdict(lambda: defaultdict(lambda: defaultdict(float))),
            WorkType.MAINTENANCE: defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
        }
        all_authors = set()
        
        for monthly_report in report.monthly_reports:
            quarter = self._get_quarter(monthly_report.month)
            
            for entry in monthly_report.entries:
                # Filter by active status if specified
                if self.filter_active_only and not entry.author.active:
                    continue
                
                pc = entry.project_component
                author = entry.author
                work_type = entry.work_type
                
                # Only track Development and Maintenance
                if work_type in [WorkType.DEVELOPMENT, WorkType.MAINTENANCE]:
                    data_by_type[work_type][pc][author][quarter] += entry.hours
                    all_authors.add(author)
        
        # Sort authors by display name
        sorted_authors = sorted(all_authors, key=lambda a: a.display_name)
        
        # Write CSV with separate sections
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header row - format names in Title Case with quarters
            header = ['Project', 'Component']
            for author in sorted_authors:
                for quarter in range(1, 5):
                    header.append(f"{author.display_name.title()} Q{quarter}")
            
            # Write Development section
            writer.writerow(['DEVELOPMENT'])
            writer.writerow(header)
            
            dev_data = data_by_type[WorkType.DEVELOPMENT]
            sorted_dev_pcs = sorted(dev_data.keys(), key=lambda pc: (pc.project, pc.component.name))
            
            for pc in sorted_dev_pcs:
                row = [pc.project, pc.component.name]
                for author in sorted_authors:
                    for quarter in range(1, 5):
                        hours = dev_data[pc].get(author, {}).get(quarter, 0)
                        row.append(f"{hours:.1f}" if hours > 0 else "")
                writer.writerow(row)
            
            # Development total row
            dev_total_row = ['TOTAL', '']
            for author in sorted_authors:
                for quarter in range(1, 5):
                    total_hours = sum(dev_data[pc].get(author, {}).get(quarter, 0) for pc in sorted_dev_pcs)
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
                    for quarter in range(1, 5):
                        hours = maint_data[pc].get(author, {}).get(quarter, 0)
                        row.append(f"{hours:.1f}" if hours > 0 else "")
                writer.writerow(row)
            
            # Maintenance total row
            maint_total_row = ['TOTAL', '']
            for author in sorted_authors:
                for quarter in range(1, 5):
                    total_hours = sum(maint_data[pc].get(author, {}).get(quarter, 0) for pc in sorted_maint_pcs)
                    maint_total_row.append(f"{total_hours:.1f}" if total_hours > 0 else "")
            writer.writerow(maint_total_row)
        
        logger.info(f"Quarterly CSV report exported to {self.output_path}")
        logger.info(f"  Development rows: {len(sorted_dev_pcs)}, Maintenance rows: {len(sorted_maint_pcs)}")
        
        return self.output_path
    
    def export_monthly(self, report) -> Path:
        """Export monthly report - not used for quarterly breakdown"""
        raise NotImplementedError("Quarterly breakdown exporter only supports yearly reports")
