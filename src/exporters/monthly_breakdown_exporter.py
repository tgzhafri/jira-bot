"""
Monthly breakdown CSV exporter for individual user reports
"""

import csv
import logging
from pathlib import Path
from collections import defaultdict
from typing import Dict, List
from calendar import month_name

from .base_exporter import BaseExporter
from ..models import TimeEntry, ProjectComponent

logger = logging.getLogger(__name__)


class MonthlyBreakdownExporter(BaseExporter):
    """Export monthly breakdown reports to CSV format"""
    
    def export_monthly_breakdown(
        self,
        year: int,
        project_keys: List[str],
        entries_by_month: Dict[int, List[TimeEntry]],
        processor
    ) -> Path:
        """Export monthly breakdown report for a single user
        
        Format:
        Project | Component | Jan | Feb | Mar | ... | Dec | Total
        """
        
        self._ensure_directory()
        
        # Aggregate data for each month
        # Structure: {ProjectComponent: {month: hours}}
        data = defaultdict(lambda: defaultdict(float))
        
        for month, entries in entries_by_month.items():
            # Aggregate entries for this month
            aggregated = processor.aggregate_entries(entries)
            for entry in aggregated.values():
                pc = entry.project_component
                data[pc][month] += entry.hours
        
        # Calculate totals for each project-component
        totals = {}
        for pc, month_hours in data.items():
            totals[pc] = sum(month_hours.values())
        
        # Write CSV
        with open(self.output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Header: Project, Component, Jan-Dec, Total
            month_names = [month_name[i][:3] for i in range(1, 13)]  # Jan, Feb, Mar, etc.
            header = ['Project', 'Component'] + month_names + ['Total']
            writer.writerow(header)
            
            # Data rows - sorted by project then component
            sorted_pcs = sorted(data.keys(), key=lambda pc: (pc.project, pc.component.name))
            
            for pc in sorted_pcs:
                row = [pc.project, pc.component.name]
                
                # Add hours for each month
                for month in range(1, 13):
                    hours = data[pc].get(month, 0)
                    row.append(f"{hours:.1f}" if hours > 0 else "")
                
                # Add total
                row.append(f"{totals[pc]:.1f}")
                
                writer.writerow(row)
            
            # Add summary row
            writer.writerow([])  # Empty row
            summary_row = ['TOTAL', '']
            for month in range(1, 13):
                month_total = sum(data[pc].get(month, 0) for pc in sorted_pcs)
                summary_row.append(f"{month_total:.1f}" if month_total > 0 else "")
            
            grand_total = sum(totals.values())
            summary_row.append(f"{grand_total:.1f}")
            writer.writerow(summary_row)
        
        logger.info(f"Monthly breakdown CSV exported to {self.output_path}")
        logger.info(f"  Rows: {len(data)}, Total hours: {grand_total:.1f}h")
        
        return self.output_path
