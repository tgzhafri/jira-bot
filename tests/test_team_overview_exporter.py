#!/usr/bin/env python3
"""
Unit tests for YearlyOverviewExporter
"""

import sys
import pytest
from pathlib import Path
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.exporters import YearlyOverviewExporter
from src.models import (
    YearlyReport, MonthlyReport, TimeEntry,
    ProjectComponent, Component, Author, WorkType
)


@pytest.fixture
def sample_yearly_report():
    """Create a sample yearly report with multiple users"""
    author1 = Author(email="john@example.com", display_name="John Doe")
    author2 = Author(email="jane@example.com", display_name="Jane Smith")
    
    pc1 = ProjectComponent(project="TEST", component=Component(name="Backend"))
    pc2 = ProjectComponent(project="TEST", component=Component(name="Frontend"))
    
    entries = [
        TimeEntry(
            project_component=pc1,
            author=author1,
            hours=10.0,
            work_type=WorkType.DEVELOPMENT
        ),
        TimeEntry(
            project_component=pc1,
            author=author2,
            hours=15.0,
            work_type=WorkType.DEVELOPMENT
        ),
        TimeEntry(
            project_component=pc2,
            author=author1,
            hours=8.0,
            work_type=WorkType.DEVELOPMENT
        ),
        TimeEntry(
            project_component=pc2,
            author=author2,
            hours=12.0,
            work_type=WorkType.DEVELOPMENT
        ),
    ]
    
    monthly = MonthlyReport(
        year=2025,
        month=1,
        project_keys=["TEST"],
        entries=entries
    )
    
    return YearlyReport(
        year=2025,
        project_keys=["TEST"],
        monthly_reports=[monthly]
    )


def test_export_yearly_with_total_row(sample_yearly_report, tmp_path):
    """Test that export_yearly adds a TOTAL row"""
    output_path = tmp_path / "test_report.csv"
    exporter = YearlyOverviewExporter(output_path)
    
    result = exporter.export_yearly(sample_yearly_report)
    
    assert result.exists()
    
    # Read and verify content
    with open(result, 'r') as f:
        lines = f.readlines()
    
    # Check header
    assert "Project,Component,Jane Smith,John Doe" in lines[0]
    
    # Check data rows
    assert "TEST,Backend,15.0,10.0" in lines[1]
    assert "TEST,Frontend,12.0,8.0" in lines[2]
    
    # Check for empty row
    assert lines[3].strip() == ""
    
    # Check TOTAL row
    assert "TOTAL,,27.0,18.0" in lines[4]
    
    print("✅ TOTAL row correctly added to CSV")


def test_export_yearly_total_calculation(sample_yearly_report, tmp_path):
    """Test that TOTAL row calculations are correct"""
    output_path = tmp_path / "test_report.csv"
    exporter = YearlyOverviewExporter(output_path)
    
    result = exporter.export_yearly(sample_yearly_report)
    
    # Read CSV
    with open(result, 'r') as f:
        lines = f.readlines()
    
    # Parse TOTAL row
    total_line = lines[4].strip()
    parts = total_line.split(',')
    
    assert parts[0] == "TOTAL"
    assert parts[1] == ""
    
    # Jane Smith total: 15.0 + 12.0 = 27.0
    assert float(parts[2]) == 27.0
    
    # John Doe total: 10.0 + 8.0 = 18.0
    assert float(parts[3]) == 18.0
    
    print("✅ TOTAL row calculations are correct")


def test_export_monthly_with_total_row(tmp_path):
    """Test that export_monthly adds a TOTAL row"""
    author1 = Author(email="john@example.com", display_name="John Doe")
    author2 = Author(email="jane@example.com", display_name="Jane Smith")
    
    pc1 = ProjectComponent(project="TEST", component=Component(name="Backend"))
    
    entries = [
        TimeEntry(
            project_component=pc1,
            author=author1,
            hours=10.0,
            work_type=WorkType.DEVELOPMENT
        ),
        TimeEntry(
            project_component=pc1,
            author=author2,
            hours=15.0,
            work_type=WorkType.DEVELOPMENT
        ),
    ]
    
    monthly = MonthlyReport(
        year=2025,
        month=1,
        project_keys=["TEST"],
        entries=entries
    )
    
    output_path = tmp_path / "test_monthly.csv"
    exporter = YearlyOverviewExporter(output_path)
    
    result = exporter.export_monthly(monthly)
    
    assert result.exists()
    
    # Read and verify
    with open(result, 'r') as f:
        lines = f.readlines()
    
    # Check for TOTAL row
    assert len(lines) >= 4  # header + data + empty + total
    assert "TOTAL" in lines[-1]
    
    print("✅ TOTAL row added to monthly export")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
