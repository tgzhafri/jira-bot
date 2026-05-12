import json
import logging
import zipfile
import io
import os
import tempfile
from typing import List, Dict, Optional, Callable, Union
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from .jira_client import JiraClient

logger = logging.getLogger(__name__)

class BackupService:
    """Service for exporting Jira project data with optimizations"""
    
    def __init__(self, client: JiraClient):
        self.client = client
        self.max_workers = getattr(client.config, 'max_workers', 10)

    def export_project(
        self, 
        project_keys: Union[str, List[str]], 
        include_comments: bool = True,
        include_worklogs: bool = True,
        include_attachments: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> str:
        """
        Export data for one or more projects to a temporary ZIP file.
        Returns the path to the temporary ZIP file.
        """
        
        if isinstance(project_keys, str):
            keys = [project_keys]
            is_bulk = False
        else:
            keys = project_keys
            is_bulk = True

        logger.info(f"Starting optimized backup for projects: {keys}")
        
        # Create a temporary file for the ZIP
        fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        
        try:
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                total_projects = len(keys)
                
                for p_idx, project_key in enumerate(keys):
                    project_progress_base = p_idx / total_projects
                    project_progress_weight = 1.0 / total_projects
                    
                    def sub_progress(p, text):
                        if progress_callback:
                            total_p = project_progress_base + (p * project_progress_weight)
                            prefix = f"[{project_key}] " if is_bulk else ""
                            progress_callback(total_p, f"{prefix}{text}")

                    if progress_callback:
                        sub_progress(0.05, f"Fetching project details...")
                        
                    # 1. Fetch project details
                    project_data = self.client.get_project(project_key)
                    
                    # Path inside ZIP
                    zip_prefix = f"{project_key}/" if is_bulk else ""
                    zf.writestr(f"{zip_prefix}project.json", json.dumps(project_data, indent=2))
                    
                    if progress_callback:
                        sub_progress(0.1, "Fetching issue list...")
                        
                    # 2. Fetch all issues
                    raw_issues = self.client.get_issues_by_project(project_key)
                    total_issues = len(raw_issues)
                    
                    if progress_callback:
                        sub_progress(0.2, f"Found {total_issues} issues. Processing...")

                    # 3. Process issues in parallel
                    processed_issues = []
                    
                    def process_single_issue(issue):
                        issue_key = issue['key']
                        if include_comments:
                            issue['comments'] = self.client.get_issue_comments(issue_key)
                        if include_worklogs:
                            issue['worklogs'] = self.client.get_all_worklogs_for_issue(issue_key)
                        
                        if include_attachments and 'attachment' in issue.get('fields', {}):
                            attachments = issue['fields']['attachment']
                            for att in attachments:
                                try:
                                    att_content = self.client.download_attachment(att['content'])
                                    # Store in ZIP: {prefix}attachments/{issue_key}/{filename}
                                    att_path = f"{zip_prefix}attachments/{issue_key}/{att['filename']}"
                                    att['local_path'] = att_path
                                    att['_content'] = att_content 
                                except Exception as e:
                                    logger.error(f"Failed to download attachment {att['filename']} for {issue_key}: {e}")
                        return issue

                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        futures = {executor.submit(process_single_issue, issue): issue for issue in raw_issues}
                        
                        for i, future in enumerate(as_completed(futures)):
                            enriched_issue = future.result()
                            
                            # Write attachments to ZIP
                            if include_attachments and 'attachment' in enriched_issue.get('fields', {}):
                                for att in enriched_issue['fields']['attachment']:
                                    if '_content' in att:
                                        zf.writestr(att['local_path'], att['_content'])
                                        del att['_content'] 
                            
                            processed_issues.append(enriched_issue)
                            
                            if progress_callback and (i + 1) % 10 == 0:
                                progress = 0.2 + (0.7 * ((i + 1) / total_issues))
                                sub_progress(progress, f"Processed {i+1}/{total_issues} issues...")

                    # 4. Write all issues to a single JSON in the ZIP
                    zf.writestr(f"{zip_prefix}issues.json", json.dumps(processed_issues, indent=2))
                
                # 5. Write global metadata
                metadata = {
                    "projects": keys,
                    "exported_at": datetime.now().isoformat(),
                    "total_projects": total_projects,
                    "includes": {
                        "comments": include_comments,
                        "worklogs": include_worklogs,
                        "attachments": include_attachments
                    }
                }
                zf.writestr("metadata.json", json.dumps(metadata, indent=2))

            if progress_callback:
                progress_callback(1.0, "Backup complete!")
                
            return temp_zip_path

        except Exception as e:
            logger.exception("Backup failed")
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            raise e

    def create_backup_zip(self, export_data: Dict) -> bytes:
        """Legacy method for backward compatibility"""
        project_key = export_data['metadata']['project_key']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"jira_backup_{project_key}_{timestamp}.json"
        
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, json.dumps(export_data, indent=2))
        
        return buf.getvalue()

    def create_backup_json(self, export_data: Dict) -> str:
        """Legacy method for backward compatibility"""
        return json.dumps(export_data, indent=2)
