"""
Jira project backup service.

Optimized for performance with:
- Streaming ZIP writes (attachments written directly, not held in memory)
- Parallel issue enrichment (comments, worklogs, attachments)
- Chunked processing with progress reporting
- Rate-limit aware attachment downloads
"""

import io
import json
import logging
import os
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
from typing import Callable, Dict, List, Optional, Union

from .jira_client import JiraClient

logger = logging.getLogger(__name__)

# Fields needed for backup (avoid fetching unnecessary data)
BACKUP_ISSUE_FIELDS = (
    "key,summary,status,issuetype,priority,assignee,reporter,"
    "created,updated,components,labels,attachment,description,"
    "fixVersions,resolution,resolutiondate"
)


class JiraBackupService:
    """Service for exporting Jira project data with optimizations.

    Performance features:
    - Uses larger page sizes for bulk issue fetching
    - Parallel enrichment of issues (comments + worklogs + attachments)
    - Streaming attachment writes to ZIP (no full in-memory accumulation)
    - Thread-safe ZIP writing with lock
    - Configurable concurrency to avoid rate limiting
    """

    def __init__(self, client: JiraClient):
        self.client = client
        self.max_workers = getattr(client.config, "max_workers", 10)

    def export_project(
        self,
        project_keys: Union[str, List[str]],
        include_comments: bool = True,
        include_worklogs: bool = True,
        include_attachments: bool = True,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> str:
        """Export data for one or more projects to a temporary ZIP file.

        Optimizations over previous implementation:
        - Fetches issues with minimal fields (BACKUP_ISSUE_FIELDS)
        - Uses larger page size (200) for fewer API calls
        - Streams attachment bytes directly into ZIP (thread-safe)
        - Processes issues in batches for better progress reporting

        Args:
            project_keys: Single project key or list of keys.
            include_comments: Include all issue comments.
            include_worklogs: Include all worklog entries.
            include_attachments: Download and include attachment files.
            progress_callback: Optional callback(progress_float, status_text).

        Returns:
            Path to the temporary ZIP file.
        """
        if isinstance(project_keys, str):
            keys = [project_keys]
            is_bulk = False
        else:
            keys = project_keys
            is_bulk = True

        logger.info("Starting optimized backup for projects: %s", keys)

        # Create a temporary file for the ZIP
        fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)

        try:
            # Lock for thread-safe ZIP writing
            zip_lock = Lock()

            with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                total_projects = len(keys)

                for p_idx, project_key in enumerate(keys):
                    project_progress_base = p_idx / total_projects
                    project_progress_weight = 1.0 / total_projects

                    def sub_progress(p, text):
                        if progress_callback:
                            total_p = project_progress_base + (p * project_progress_weight)
                            prefix = "[{}] ".format(project_key) if is_bulk else ""
                            progress_callback(total_p, "{}{}".format(prefix, text))

                    sub_progress(0.05, "Fetching project details...")

                    # 1. Fetch project details
                    project_data = self.client.get_project(project_key)

                    # Path inside ZIP
                    zip_prefix = "{}/".format(project_key) if is_bulk else ""
                    with zip_lock:
                        zf.writestr(
                            "{}project.json".format(zip_prefix),
                            json.dumps(project_data, indent=2),
                        )

                    sub_progress(0.1, "Fetching issue list...")

                    # 2. Fetch all issues with optimized fields and larger page size
                    raw_issues = self.client.get_issues_by_project_chunked(
                        project_key,
                        fields=BACKUP_ISSUE_FIELDS,
                        chunk_size=200,
                    )
                    total_issues = len(raw_issues)

                    sub_progress(0.2, "Found {} issues. Processing...".format(total_issues))

                    if total_issues == 0:
                        with zip_lock:
                            zf.writestr(
                                "{}issues.json".format(zip_prefix),
                                json.dumps([], indent=2),
                            )
                        continue

                    # 3. Process issues in parallel with streaming attachment writes
                    processed_issues = []
                    processed_count = [0]  # Mutable for closure

                    def process_single_issue(issue):
                        """Enrich a single issue and stream attachments to ZIP."""
                        issue_key = issue["key"]

                        if include_comments:
                            issue["comments"] = self.client.get_issue_comments(issue_key)
                        if include_worklogs:
                            issue["worklogs"] = self.client.get_all_worklogs_for_issue(issue_key)

                        if include_attachments and "attachment" in issue.get("fields", {}):
                            attachments = issue["fields"]["attachment"]
                            for att in attachments:
                                try:
                                    att_content = self.client.download_attachment(att["content"])
                                    att_path = "{}attachments/{}/{}".format(
                                        zip_prefix, issue_key, att["filename"]
                                    )
                                    att["local_path"] = att_path
                                    # Write attachment directly to ZIP (thread-safe)
                                    with zip_lock:
                                        zf.writestr(att_path, att_content)
                                except Exception as e:
                                    logger.error(
                                        "Failed to download attachment %s for %s: %s",
                                        att["filename"], issue_key, e,
                                    )

                        return issue

                    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                        futures = {
                            executor.submit(process_single_issue, issue): issue
                            for issue in raw_issues
                        }

                        for future in as_completed(futures):
                            try:
                                enriched_issue = future.result()
                                # Remove binary content from issue data before JSON serialization
                                if include_attachments and "attachment" in enriched_issue.get("fields", {}):
                                    for att in enriched_issue["fields"]["attachment"]:
                                        att.pop("_content", None)
                                processed_issues.append(enriched_issue)
                            except Exception as e:
                                logger.error("Failed to process issue: %s", e)

                            processed_count[0] += 1
                            if progress_callback and processed_count[0] % 10 == 0:
                                progress = 0.2 + (0.7 * (processed_count[0] / total_issues))
                                sub_progress(
                                    progress,
                                    "Processed {}/{} issues...".format(
                                        processed_count[0], total_issues
                                    ),
                                )

                    # 4. Write all issues to a single JSON in the ZIP
                    with zip_lock:
                        zf.writestr(
                            "{}issues.json".format(zip_prefix),
                            json.dumps(processed_issues, indent=2),
                        )

                # 5. Write global metadata
                metadata = {
                    "projects": keys,
                    "exported_at": datetime.now().isoformat(),
                    "total_projects": total_projects,
                    "includes": {
                        "comments": include_comments,
                        "worklogs": include_worklogs,
                        "attachments": include_attachments,
                    },
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
        """Legacy method for backward compatibility."""
        project_key = export_data["metadata"]["project_key"]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = "jira_backup_{}_{}.json".format(project_key, timestamp)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, json.dumps(export_data, indent=2))

        return buf.getvalue()

    def create_backup_json(self, export_data: Dict) -> str:
        """Legacy method for backward compatibility."""
        return json.dumps(export_data, indent=2)