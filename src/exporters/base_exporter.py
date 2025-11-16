"""
Base exporter class for all export formats
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import YearlyReport, MonthlyReport


class BaseExporter(ABC):
    """Abstract base class for exporters"""
    
    def __init__(self, output_path: Path):
        self.output_path = output_path
    
    @abstractmethod
    def export_yearly(self, report: YearlyReport) -> Path:
        """Export yearly report"""
        pass
    
    @abstractmethod
    def export_monthly(self, report: MonthlyReport) -> Path:
        """Export monthly report"""
        pass
    
    def _ensure_directory(self):
        """Ensure output directory exists"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
