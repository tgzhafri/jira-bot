"""
Configuration management for Automate Jira
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class JiraConfig:
    """Jira connection configuration
    
    Note: username (email) is required for Jira Cloud Basic Authentication.
    The API uses email + API token for authentication.
    Reference: https://developer.atlassian.com/cloud/jira/platform/basic-auth-for-rest-apis/
    """
    url: str
    username: str  # Email address - required for Basic Auth
    api_token: str
    project_keys: Optional[List[str]] = None  # None means fetch all projects
    enable_cache: bool = True
    cache_dir: str = ".cache"
    max_workers: int = 8  # For parallel processing
    
    @classmethod
    def from_env(cls) -> "JiraConfig":
        """Load configuration from environment variables"""
        url = os.getenv('JIRA_URL')
        username = os.getenv('JIRA_USERNAME')
        api_token = os.getenv('JIRA_API_TOKEN')
        project_keys_str = os.getenv('JIRA_PROJECT_KEY', '')
        
        if not all([url, username, api_token]):
            raise ValueError(
                "Missing required environment variables. "
                "Please set JIRA_URL, JIRA_USERNAME, and JIRA_API_TOKEN"
            )
        
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
            url=url.rstrip('/'),
            username=username,
            api_token=api_token,
            project_keys=project_keys,
            enable_cache=enable_cache,
            cache_dir=cache_dir,
            max_workers=max_workers
        )
    
    def validate(self) -> bool:
        """Validate configuration"""
        if not self.url.startswith(('http://', 'https://')):
            raise ValueError(f"Invalid JIRA_URL: {self.url}")
        
        if not self.username or '@' not in self.username:
            raise ValueError(f"Invalid JIRA_USERNAME: {self.username}")
        
        if not self.api_token or len(self.api_token) < 10:
            raise ValueError("Invalid JIRA_API_TOKEN")
        
        # project_keys can be None (fetch all projects)
        
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
        jira: Optional[JiraConfig] = None,
        report: Optional[ReportConfig] = None,
        export: Optional[ExportConfig] = None
    ):
        self.jira = jira or JiraConfig.from_env()
        self.report = report or ReportConfig.default()
        self.export = export or ExportConfig()
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load all configuration from environment"""
        return cls(
            jira=JiraConfig.from_env(),
            report=ReportConfig.default(),
            export=ExportConfig()
        )
    
    def validate(self) -> bool:
        """Validate all configuration"""
        return self.jira.validate()
