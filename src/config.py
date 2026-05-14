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


def _get_atlassian_env(new_key: str, old_key: str, default: str = "") -> str:
    """Get an environment variable with fallback to deprecated name.

    Prefers the new ATLASSIAN_* key. Falls back to the legacy JIRA_* key
    and logs a deprecation warning if the old key is used.
    """
    value = os.getenv(new_key)
    if value:
        return value

    legacy_value = os.getenv(old_key)
    if legacy_value:
        logger.warning(
            f"Environment variable '{old_key}' is deprecated. "
            f"Please rename it to '{new_key}'."
        )
        return legacy_value

    return default


@dataclass
class AtlassianConfig:
    """Shared Atlassian Cloud connection configuration.

    Used by both Jira and Confluence clients since they share the same
    authentication credentials (email + API token against the same instance).
    """
    url: str
    username: str  # Email address for Basic Auth
    api_token: str

    @classmethod
    def from_env(cls) -> "AtlassianConfig":
        """Load configuration from environment variables.

        Supports both new ATLASSIAN_* and legacy JIRA_* env var names.
        Legacy names trigger a deprecation warning in the logs.
        """
        url = _get_atlassian_env('ATLASSIAN_URL', 'JIRA_URL').strip()
        username = _get_atlassian_env('ATLASSIAN_USERNAME', 'JIRA_USERNAME').strip()
        api_token = _get_atlassian_env('ATLASSIAN_API_TOKEN', 'JIRA_API_TOKEN').strip()

        if not url:
            raise ValueError("Missing required environment variable: ATLASSIAN_URL")
        if not username:
            raise ValueError("Missing required environment variable: ATLASSIAN_USERNAME")
        if not api_token:
            raise ValueError("Missing required environment variable: ATLASSIAN_API_TOKEN")
        if not url.startswith(('http://', 'https://')):
            raise ValueError("Invalid ATLASSIAN_URL format: must start with http:// or https://")

        return cls(url=url.rstrip('/'), username=username, api_token=api_token)

    @classmethod
    def from_dict(cls, data: dict) -> "AtlassianConfig":
        """Load configuration from a dictionary (e.g. UI-driven)"""
        return cls(
            url=data.get('url', '').rstrip('/'),
            username=data.get('username', ''),
            api_token=data.get('api_token', ''),
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


# Backward-compatible alias — existing code importing ConfluenceConfig still works
ConfluenceConfig = AtlassianConfig


@dataclass
class JiraConfig(AtlassianConfig):
    """Jira-specific connection configuration.

    Extends AtlassianConfig with Jira-specific settings like project keys,
    caching, and parallelism.

    Note: username (email) is required for Jira Cloud Basic Authentication.
    Reference: https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/
    """
    project_keys: Optional[List[str]] = None  # None means fetch all projects
    enable_cache: bool = True
    cache_dir: str = ".cache"
    max_workers: int = 8  # For parallel processing

    @classmethod
    def from_env(cls) -> "JiraConfig":
        """Load configuration from environment variables.

        Supports both new ATLASSIAN_* and legacy JIRA_* env var names.
        Legacy names trigger a deprecation warning in the logs.
        """
        url = _get_atlassian_env('ATLASSIAN_URL', 'JIRA_URL')
        username = _get_atlassian_env('ATLASSIAN_USERNAME', 'JIRA_USERNAME')
        api_token = _get_atlassian_env('ATLASSIAN_API_TOKEN', 'JIRA_API_TOKEN')
        project_keys_str = os.getenv('JIRA_PROJECT_KEY', '')

        # If JIRA_PROJECT_KEY is empty or not set, project_keys will be None (fetch all)
        project_keys = None
        if project_keys_str:
            project_keys = [key.strip() for key in project_keys_str.split(',') if key.strip()]
            if not project_keys:
                project_keys = None  # Empty after parsing means fetch all

        # Performance settings
        enable_cache = os.getenv('JIRA_ENABLE_CACHE', 'true').lower() in ('true', '1', 'yes')
        cache_dir = os.getenv('JIRA_CACHE_DIR', '.cache')
        max_workers = int(os.getenv('JIRA_MAX_WORKERS', '8'))

        return cls(
            url=(url or "").rstrip('/'),
            username=username or "",
            api_token=api_token or "",
            project_keys=project_keys,
            enable_cache=enable_cache,
            cache_dir=cache_dir,
            max_workers=max_workers,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "JiraConfig":
        """Load configuration from a dictionary"""
        return cls(
            url=data.get('url', '').rstrip('/'),
            username=data.get('username', ''),
            api_token=data.get('api_token', ''),
            project_keys=data.get('project_keys'),
            enable_cache=data.get('enable_cache', True),
            cache_dir=data.get('cache_dir', '.cache'),
            max_workers=data.get('max_workers', 8),
        )


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
        jira: Optional[JiraConfig] = None,
        atlassian: Optional[AtlassianConfig] = None,
        report: Optional[ReportConfig] = None,
        export: Optional[ExportConfig] = None,
    ):
        self.jira = jira or JiraConfig.from_env()
        # Shared Atlassian credentials — defaults to the Jira config's base fields
        self.atlassian = atlassian or AtlassianConfig(
            url=self.jira.url,
            username=self.jira.username,
            api_token=self.jira.api_token,
        )
        self.report = report or ReportConfig.default()
        self.export = export or ExportConfig()

    @classmethod
    def from_env(cls) -> "Config":
        """Load all configuration from environment"""
        return cls(
            jira=JiraConfig.from_env(),
            report=ReportConfig.default(),
            export=ExportConfig(),
        )

    def validate(self) -> bool:
        """Validate all configuration"""
        return self.jira.validate()
