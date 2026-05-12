import json
import logging
import zipfile
import io
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
from .jira_client import JiraClient

logger = logging.getLogger(__name__)

class BackupService:
    """Service for exporting Jira project data"""
    
    def __init__(self, client: JiraClient):
        self.client = client

    def export_project(
        self, 
        project_key: str, 
        include_comments: bool = True,
        include_worklogs: bool = True,
        include_attachments_metadata: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """Export all data for a project as a dictionary"""
        
        logger.info(f"Starting backup for project {project_key}")
        
        if progress_callback:
            progress_callback(0.1, f"Fetching project details for {project_key}...")
            
        # 1. Fetch project details
        project_data = self.client.get_project(project_key)
        
        if progress_callback:
            progress_callback(0.2, "Fetching issues...")
            
        # 2. Fetch all issues
        issues = self.client.get_issues_by_project(project_key)
        total_issues = len(issues)
        
        if progress_callback:
            progress_callback(0.3, f"Fetched {total_issues} issues. Processing details...")
            
        # 3. Enrich issues with comments and worklogs if requested
        for i, issue in enumerate(issues):
            issue_key = issue['key']
            
            if progress_callback and i % 10 == 0:
                progress = 0.3 + (0.5 * (i / total_issues))
                progress_callback(progress, f"Processing issue {i+1}/{total_issues}: {issue_key}")
            
            if include_comments:
                issue['comments'] = self.client.get_issue_comments(issue_key)
            
            if include_worklogs:
                issue['worklogs'] = self.client.get_all_worklogs_for_issue(issue_key)
                
            if not include_attachments_metadata:
                # Remove attachments metadata if not requested (it's in fields by default with *all)
                if 'attachment' in issue['fields']:
                    del issue['fields']['attachment']
        
        if progress_callback:
            progress_callback(0.9, "Finalizing export data...")

        
        export_data = {
            "metadata": {
                "project_key": project_key,
                "exported_at": datetime.now().isoformat(),
                "issue_count": len(issues)
            },
            "project": project_data,
            "issues": issues
        }
        
        return export_data

    def create_backup_zip(self, export_data: Dict) -> bytes:
        """Create a ZIP archive containing the export data as JSON"""
        project_key = export_data['metadata']['project_key']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"jira_backup_{project_key}_{timestamp}.json"
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, json.dumps(export_data, indent=2))
        
        return buf.getvalue()

    def create_backup_json(self, export_data: Dict) -> str:
        """Convert export data to JSON string"""
        return json.dumps(export_data, indent=2)
