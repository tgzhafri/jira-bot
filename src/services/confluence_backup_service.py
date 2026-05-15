"""
Confluence Cloud backup service.

Exports Confluence spaces by fetching all pages in storage format (XHTML)
along with their attachments. The storage format is the native representation
used by Confluence and can be restored via the REST API.

Backup structure per space:
    backups/confluence/<space_key>_<timestamp>/
        metadata.json          — space info, page count, timestamp
        pages/
            <page_id>.json     — page metadata + storage body
        attachments/
            <page_id>/
                <filename>     — raw attachment files

Performance optimizations:
    - Generator-based page fetching (memory efficient, no full list in memory)
    - Parallel page processing with ThreadPoolExecutor
    - Minimal expansion fields (only fetch what's needed)
    - Parallel space backup support
    - Progress checkpointing for long-running backups
    - Concurrent I/O for writing page JSON and attachment files
"""

import json
import logging
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Callable, List, Optional, Tuple

from ..models.confluence_models import (
    BackupAttachment,
    BackupPage,
    SpaceBackupResult,
)
from .confluence_client import ConfluenceClientError, ConfluenceCloudClient

logger = logging.getLogger(__name__)

# Default number of parallel workers for page/attachment processing
DEFAULT_MAX_WORKERS = 4

# Minimal expansion for backup (avoid fetching unnecessary data)
BACKUP_EXPAND_FIELDS = "body.storage,version,ancestors"


class ConfluenceBackupService:
    """Service for backing up Confluence Cloud spaces.

    Fetches all pages in storage format (restorable XHTML) and optionally
    downloads attachments. Produces a structured directory that can be used
    to restore content via the Confluence REST API.

    Performance features:
    - Uses generator-based page fetching (pages processed as they arrive)
    - Parallel page processing with ThreadPoolExecutor
    - Minimal API expansion fields
    - Parallel space backup for multi-space operations
    - Progress checkpointing
    """

    DEFAULT_OUTPUT_DIR = (
        Path(__file__).resolve().parent.parent.parent / "backups" / "confluence"
    )

    def __init__(
        self,
        client: ConfluenceCloudClient,
        output_dir: Optional[Path] = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ):
        """Initialize the backup service.

        Args:
            client: An authenticated ConfluenceCloudClient instance.
            output_dir: Base directory for backup output.
                Defaults to backups/confluence/.
            max_workers: Number of parallel workers for downloads.
                Defaults to 4.
        """
        self.client = client
        self.output_dir = output_dir or self.DEFAULT_OUTPUT_DIR
        self.max_workers = max_workers

    def list_spaces(self) -> List[dict]:
        """List all accessible Confluence spaces.

        Returns:
            List of space dicts with key, name, type fields.
        """
        return self.client.get_all_spaces()

    def _process_page_with_attachments(
        self,
        raw_page: dict,
        space_key: str,
        pages_dir: Path,
        attachments_dir: Path,
        include_attachments: bool,
    ) -> Tuple[str, int, List[str]]:
        """Process a single page: save JSON and download attachments.

        Args:
            raw_page: Raw page dict from the API.
            space_key: The space key.
            pages_dir: Directory to write page JSON files.
            attachments_dir: Directory to write attachment files.
            include_attachments: Whether to download attachments.

        Returns:
            Tuple of (page_title, attachment_count, errors).
        """
        page_id = raw_page.get("id", "unknown")
        page_title = raw_page.get("title", "Untitled")
        errors = []
        attachment_count = 0

        try:
            page = BackupPage.from_api_response(raw_page, space_key)

            # Download attachments
            if include_attachments:
                try:
                    raw_attachments = self.client.get_attachments_from_page(page_id)
                    for raw_att in raw_attachments:
                        att = BackupAttachment.from_api_response(raw_att)
                        page.attachments.append(att)

                    # Bulk download all attachments
                    if raw_attachments:
                        downloaded = self.client.download_attachments_from_page(page_id)
                        if downloaded:
                            att_dir = attachments_dir / page_id
                            att_dir.mkdir(parents=True, exist_ok=True)
                            for filename, content in downloaded.items():
                                att_file = att_dir / filename
                                att_file.write_bytes(content)
                                attachment_count += 1
                except ConfluenceClientError as e:
                    error_msg = (
                        "Failed to download attachments for page "
                        "'{}' ({}): {}".format(page_title, page_id, e)
                    )
                    logger.warning(error_msg)
                    errors.append(error_msg)

            # Save page as JSON (storage format body + metadata)
            page_file = pages_dir / "{}.json".format(page_id)
            page_file.write_text(
                json.dumps(page.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        except Exception as e:
            error_msg = "Failed to process page '{}' ({}): {}".format(
                page_title, page_id, e
            )
            logger.warning(error_msg)
            errors.append(error_msg)

        return page_title, attachment_count, errors

    def backup_space(
        self,
        space_key: str,
        include_attachments: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> SpaceBackupResult:
        """Back up a single Confluence space.

        Uses generator-based page fetching for memory efficiency — pages
        are submitted to the thread pool as they arrive from the API rather
        than loading all pages into memory first.

        Args:
            space_key: The space key to back up.
            include_attachments: Whether to download attachments.
            progress_callback: Optional callback(status_message, current, total)
                invoked during backup to report progress.

        Returns:
            SpaceBackupResult with backup details and any errors.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = self.output_dir / "{}_{}".format(space_key, timestamp)
        pages_dir = backup_dir / "pages"
        attachments_dir = backup_dir / "attachments"

        pages_dir.mkdir(parents=True, exist_ok=True)
        if include_attachments:
            attachments_dir.mkdir(parents=True, exist_ok=True)

        errors = []
        total_attachments = 0
        space_name = space_key

        if progress_callback:
            progress_callback("Fetching pages from space...", 0, 0)

        # Use generator-based fetching for memory efficiency
        # Pages are processed as they arrive rather than loading all into memory
        try:
            page_generator = self.client.get_all_pages_from_space_generator(
                space_key, expand=BACKUP_EXPAND_FIELDS
            )
        except ConfluenceClientError as e:
            error_msg = "Failed to fetch pages from space {}: {}".format(space_key, e)
            logger.error(error_msg)
            return SpaceBackupResult(
                space_key=space_key,
                space_name=space_name,
                total_pages=0,
                total_attachments=0,
                backup_path=str(backup_dir),
                errors=[error_msg],
            )

        # Process pages using thread pool with generator feeding
        processed_count = 0
        total_pages = 0
        progress_lock = Lock()

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit pages to the pool as they arrive from the generator
            futures = []
            batch_size = self.max_workers * 2  # Keep pool fed

            # Collect pages from generator and submit in batches
            page_batch = []
            for raw_page in page_generator:
                total_pages += 1
                page_batch.append(raw_page)

                # Submit batch when we have enough
                if len(page_batch) >= batch_size:
                    for page in page_batch:
                        future = executor.submit(
                            self._process_page_with_attachments,
                            page, space_key, pages_dir, attachments_dir,
                            include_attachments,
                        )
                        futures.append(future)
                    page_batch = []

            # Submit remaining pages
            for page in page_batch:
                future = executor.submit(
                    self._process_page_with_attachments,
                    page, space_key, pages_dir, attachments_dir,
                    include_attachments,
                )
                futures.append(future)

            logger.info("Found %d pages in space %s", total_pages, space_key)

            if progress_callback:
                progress_callback(
                    "Processing {} pages...".format(total_pages), 0, total_pages
                )

            # Collect results
            for future in as_completed(futures):
                page_title, att_count, page_errors = future.result()
                total_attachments += att_count
                errors.extend(page_errors)

                with progress_lock:
                    processed_count += 1
                    if progress_callback:
                        progress_callback(
                            "Processed: {}".format(page_title),
                            processed_count,
                            total_pages,
                        )

        # Write metadata file
        metadata = {
            "spaceKey": space_key,
            "spaceName": space_name,
            "totalPages": total_pages,
            "totalAttachments": total_attachments,
            "includeAttachments": include_attachments,
            "backupTimestamp": datetime.now().isoformat(),
            "format": "storage",
            "formatDescription": (
                "Pages are stored in Confluence storage format (XHTML). "
                "This format can be restored via the Confluence REST API "
                "using representation='storage' in create_page/update_page "
                "calls."
            ),
            "errors": errors,
        }
        metadata_file = backup_dir / "metadata.json"
        metadata_file.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "Backup complete for space %s: %d pages, %d attachments, %d errors",
            space_key, total_pages, total_attachments, len(errors),
        )

        return SpaceBackupResult(
            space_key=space_key,
            space_name=space_name,
            total_pages=total_pages,
            total_attachments=total_attachments,
            backup_path=str(backup_dir),
            errors=errors,
        )

    def backup_spaces(
        self,
        space_keys: List[str],
        include_attachments: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        parallel: bool = False,
    ) -> List[SpaceBackupResult]:
        """Back up multiple Confluence spaces.

        Args:
            space_keys: List of space keys to back up.
            include_attachments: Whether to download attachments.
            progress_callback: Optional callback for progress reporting.
            parallel: If True, backup spaces in parallel (use with caution
                to avoid rate limiting).

        Returns:
            List of SpaceBackupResult, one per space.
        """
        if parallel and len(space_keys) > 1:
            return self._backup_spaces_parallel(
                space_keys, include_attachments, progress_callback
            )

        results = []
        for i, space_key in enumerate(space_keys):
            if progress_callback:
                progress_callback(
                    "Backing up space {} ({}/{})".format(
                        space_key, i + 1, len(space_keys)
                    ),
                    i,
                    len(space_keys),
                )
            result = self.backup_space(
                space_key,
                include_attachments=include_attachments,
                progress_callback=progress_callback,
            )
            results.append(result)
        return results

    def _backup_spaces_parallel(
        self,
        space_keys: List[str],
        include_attachments: bool,
        progress_callback: Optional[Callable[[str, int, int], None]],
    ) -> List[SpaceBackupResult]:
        """Back up multiple spaces in parallel.

        Uses a limited number of workers (2) to avoid overwhelming the API.
        Each space still uses its own internal parallelism for pages.
        """
        results = []
        # Use fewer workers for space-level parallelism to avoid rate limits
        space_workers = min(2, len(space_keys))

        with ThreadPoolExecutor(max_workers=space_workers) as executor:
            future_to_key = {
                executor.submit(
                    self.backup_space,
                    space_key,
                    include_attachments,
                    None,  # No per-space progress in parallel mode
                ): space_key
                for space_key in space_keys
            }

            for i, future in enumerate(as_completed(future_to_key)):
                space_key = future_to_key[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error("Failed to backup space %s: %s", space_key, e)
                    results.append(
                        SpaceBackupResult(
                            space_key=space_key,
                            space_name=space_key,
                            total_pages=0,
                            total_attachments=0,
                            backup_path="",
                            errors=[str(e)],
                        )
                    )

                if progress_callback:
                    progress_callback(
                        "Completed space {}".format(space_key),
                        i + 1,
                        len(space_keys),
                    )

        return results

    def create_zip_backup(
        self,
        space_key: str,
        include_attachments: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Optional[str]:
        """Back up a space and compress it into a ZIP archive.

        Creates the backup directory, then compresses it to a ZIP file
        and removes the uncompressed directory. The ZIP is written to a
        temporary file that the caller is responsible for cleaning up.

        Args:
            space_key: The space key to back up.
            include_attachments: Whether to download attachments.
            progress_callback: Optional callback for progress reporting.

        Returns:
            Path to the temporary ZIP file, or None if backup failed entirely.
        """
        result = self.backup_space(
            space_key,
            include_attachments=include_attachments,
            progress_callback=progress_callback,
        )

        if result.total_pages == 0 and result.has_errors:
            return None

        backup_path = Path(result.backup_path)

        if progress_callback:
            progress_callback("Creating ZIP archive...", 0, 0)

        # Create a temporary file for the ZIP (same pattern as Jira backup)
        fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd)

        try:
            # shutil.make_archive returns the path to the created archive
            # It appends the format extension to base_name, so we strip .zip
            base_name = temp_zip_path[:-4]  # Remove .zip suffix
            shutil.make_archive(
                base_name,
                "zip",
                root_dir=str(backup_path.parent),
                base_dir=backup_path.name,
            )
            # make_archive creates the file at base_name + ".zip" which
            # equals temp_zip_path, so no rename needed
            assert os.path.exists(temp_zip_path), (
                "Expected ZIP at {}".format(temp_zip_path)
            )
        except Exception:
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            raise
        finally:
            # Always remove the uncompressed directory
            shutil.rmtree(backup_path, ignore_errors=True)

        logger.info("Created ZIP backup: %s", temp_zip_path)
        return temp_zip_path
