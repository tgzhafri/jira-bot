"""
Configuration management for Atlassian Bot (Jira & Confluence)
"""

import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)


def _get_env(key: str, default: str = "") -> str:
    """Get an environment variable or return a default."""
    return os.getenv(key, default)


@dataclass
class AtlassianConfig:
    """Atlassian Cloud connection and operational configuration.

    Used by both Jira and Confluence clients since they share the same
    authentication credentials (email + API token against the same instance).

    Also holds operational settings (caching, parallelism, project filtering)
    that apply to report generation and data fetching.
    """
    url: str
    username: str
    api_token: str
    project_keys: Optional[List[str]] = None
    enable_cache: bool = True
    cache_dir: str = ".cache"
    max_workers: int = 8

    @classmethod
    def from_env(cls) -> "AtlassianConfig":
        """Load configuration from ATLASSIAN_* environment variables."""
        url = _get_env('ATLASSIAN_URL').strip()
        username = _get_env('ATLASSIAN_USERNAME').strip()
        api_token = _get_env('ATLASSIAN_API_TOKEN').strip()

        # Project filtering
        project_keys_str = _get_env('ATLASSIAN_PROJECT_KEYS').strip()
        project_keys = None
        if project_keys_str:
            project_keys = [
                key.strip() for key in project_keys_str.split(',') if key.strip()
            ]
            if not project_keys:
                project_keys = None

        if not url:
            raise ValueError("Missing required environment variable: ATLASSIAN_URL")
        if not username:
            raise ValueError("Missing required environment variable: ATLASSIAN_USERNAME")
        if not api_token:
            raise ValueError("Missing required environment variable: ATLASSIAN_API_TOKEN")
        if not url.startswith(('http://', 'https://')):
            raise ValueError("Invalid ATLASSIAN_URL format: must start with http:// or https://")

        return cls(
            url=url.rstrip('/'),
            username=username,
            api_token=api_token,
            project_keys=project_keys,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "AtlassianConfig":
        """Load configuration from a dictionary (e.g. UI-driven)"""
        return cls(
            url=data.get('url', '').rstrip('/'),
            username=data.get('username', ''),
            api_token=data.get('api_token', ''),
            project_keys=data.get('project_keys'),
            enable_cache=data.get('enable_cache', True),
            cache_dir=data.get('cache_dir', '.cache'),
            max_workers=data.get('max_workers', 8),
        )

    def validate(self) -> bool:
        """Validate connection credentials.

        Raises:
            ValueError: If URL, username, or API token are invalid.
        """
        if not self.url or not self.url.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid ATLASSIAN_URL: {self.url}")
        if not self.username or '@' not in self.username:
            raise ValueError(f"Invalid ATLASSIAN_USERNAME: {self.username}")
        if not self.api_token or len(self.api_token) < 10:
            raise ValueError("Invalid ATLASSIAN_API_TOKEN")
        return True


@dataclass
class ReportConfig:
    """Report generation configuration"""
    year: int
    output_dir: Path = field(default_factory=lambda: Path.cwd())
    include_tickets: bool = True
    include_weekly_breakdown: bool = True

    @classmethod
    def default(cls, year: Optional[int] = None) -> "ReportConfig":
        """Create default configuration"""
        from datetime import datetime
        return cls(year=year or datetime.now().year)


@dataclass
class ExportConfig:
    """Export format configuration"""
    format: str = "text"  # text, csv, json, excel
    filename: Optional[str] = None
    include_summary: bool = True
    include_charts: bool = False  # For Excel/HTML exports

    def get_filename(self, year: int) -> str:
        """Generate filename based on format"""
        if self.filename:
            return self.filename

        extensions = {
            'text': 'txt',
            'csv': 'csv',
            'json': 'json',
            'excel': 'xlsx',
            'html': 'html'
        }

        ext = extensions.get(self.format, 'txt')
        return f"manhour_report_{year}.{ext}"


class Config:
    """Main configuration container"""

    def __init__(
        self,
        atlassian: Optional[AtlassianConfig] = None,
        report: Optional[ReportConfig] = None,
        export: Optional[ExportConfig] = None,
    ):
        self.atlassian = atlassian or AtlassianConfig.from_env()
        self.report = report or ReportConfig.default()
        self.export = export or ExportConfig()

    @classmethod
    def from_env(cls) -> "Config":
        """Load all configuration from environment"""
        return cls(
            atlassian=AtlassianConfig.from_env(),
            report=ReportConfig.default(),
            export=ExportConfig(),
        )

    def validate(self) -> bool:
        """Validate all configuration"""
        return self.atlassian.validate()
