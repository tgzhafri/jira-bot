"""
Confluence Data Center backup service.

Orchestrates backup operations by creating jobs, polling their status,
and managing file downloads via the ConfluenceClient.
"""

import logging
import re
import time
from pathlib import Path
from typing import Callable, List, Optional

from ..models.confluence_models import (
    ConfluenceJobDetails,
    ConfluenceJobOperation,
    ConfluenceJobScope,
    ConfluenceJobState,
    parse_job_details,
)
from .confluence_client import (
    ConfluenceAPIError,
    ConfluenceClient,
    ConfluenceClientError,
    ConfluenceConnectionError,
)

logger = logging.getLogger(__name__)


class ConfluenceBackupService:
    """Service for orchestrating Confluence Data Center backup operations.

    Provides methods for creating site/space backups, polling job status,
    and downloading backup files.
    """

    DEFAULT_POLL_INTERVAL = 5  # seconds
    MAX_POLL_DURATION = 14400  # 4 hours in seconds
    MAX_POLL_RETRIES = 3
    DOWNLOAD_CHUNK_SIZE = 8192  # bytes

    # Validation pattern for space backup file_name_prefix: alphanumeric, hyphen, underscore only
    _SPACE_PREFIX_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

    def __init__(self, client: ConfluenceClient):
        """Initialize the backup service with a ConfluenceClient.

        Args:
            client: An authenticated ConfluenceClient instance.
        """
        self.client = client

    def create_site_backup(
        self,
        skip_attachments: bool = False,
        keep_permanently: bool = False,
        file_name_prefix: Optional[str] = None,
    ) -> ConfluenceJobDetails:
        """Create a full site backup of the Confluence Data Center instance.

        Sends a POST request to /backup/site with the specified parameters.

        Args:
            skip_attachments: If True, exclude attachments from the backup.
            keep_permanently: If True, retain the backup file indefinitely on the server.
            file_name_prefix: Optional custom prefix for the backup filename (max 200 chars).

        Returns:
            ConfluenceJobDetails with the job ID and initial state.

        Raises:
            ValueError: If file_name_prefix exceeds 200 characters.
            ConfluenceClientError: If the API request fails.
        """
        # Validate file_name_prefix length
        if file_name_prefix is not None and len(file_name_prefix) > 200:
            raise ValueError(
                "file_name_prefix must not exceed 200 characters, "
                f"got {len(file_name_prefix)}"
            )

        payload = {
            "skipAttachments": skip_attachments,
            "keepPermanently": keep_permanently,
            "fileNamePrefix": file_name_prefix,
        }

        logger.info(
            f"Creating site backup (skip_attachments={skip_attachments}, "
            f"keep_permanently={keep_permanently}, prefix={file_name_prefix!r})"
        )

        response = self.client._make_request("POST", "backup/site", json_data=payload)
        return parse_job_details(response.json())

    def create_space_backup(
        self,
        space_keys: List[str],
        keep_permanently: bool = False,
        file_name_prefix: Optional[str] = None,
    ) -> ConfluenceJobDetails:
        """Create a backup of specific Confluence spaces.

        Sends a POST request to /backup/space with the specified space keys
        and parameters.

        Args:
            space_keys: List of 1 to 50 space keys to back up.
            keep_permanently: If True, retain the backup file indefinitely on the server.
            file_name_prefix: Optional custom prefix (alphanumeric/hyphen/underscore only,
                max 100 chars).

        Returns:
            ConfluenceJobDetails with the job ID, initial state, and space keys.

        Raises:
            ValueError: If space_keys is empty, exceeds 50 items, or if
                file_name_prefix contains invalid characters or exceeds 100 chars.
            ConfluenceClientError: If the API request fails.
        """
        # Validate space_keys list
        if not space_keys:
            raise ValueError("space_keys must not be empty")
        if len(space_keys) > 50:
            raise ValueError(
                f"space_keys must contain at most 50 items, got {len(space_keys)}"
            )

        # Validate file_name_prefix for space backup
        if file_name_prefix is not None:
            if len(file_name_prefix) > 100:
                raise ValueError(
                    "file_name_prefix for space backup must not exceed 100 characters, "
                    f"got {len(file_name_prefix)}"
                )
            if not self._SPACE_PREFIX_PATTERN.match(file_name_prefix):
                raise ValueError(
                    "file_name_prefix for space backup must contain only "
                    "alphanumeric characters, hyphens, and underscores"
                )

        payload = {
            "spaceKeys": space_keys,
            "keepPermanently": keep_permanently,
            "fileNamePrefix": file_name_prefix,
        }

        logger.info(
            f"Creating space backup (spaces={space_keys}, "
            f"keep_permanently={keep_permanently}, prefix={file_name_prefix!r})"
        )

        response = self.client._make_request("POST", "backup/space", json_data=payload)
        return parse_job_details(response.json())

    def download_backup(
        self,
        job_id: str,
        destination: Path,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> Path:
        """Download a completed backup file to a local path.

        Streams the response in 8192-byte chunks, creating parent directories
        if needed. Removes any partially written file on failure.

        Args:
            job_id: The unique identifier of the completed backup job.
            destination: Local file path where the backup will be saved.
            progress_callback: Optional callable invoked after each chunk with
                the cumulative bytes received so far.

        Returns:
            The destination Path where the file was saved.

        Raises:
            ConfluenceClientError: If the download request fails or a network
                error occurs during streaming.
            OSError: If the file cannot be written to the destination.
        """
        logger.info(f"Downloading backup for job {job_id} to {destination}")

        # Create parent directories if they don't exist
        destination.parent.mkdir(parents=True, exist_ok=True)

        try:
            response = self.client._make_request(
                "GET", f"jobs/{job_id}/download", stream=True
            )

            bytes_received = 0
            with open(destination, "wb") as f:
                for chunk in response.iter_content(
                    chunk_size=self.DOWNLOAD_CHUNK_SIZE
                ):
                    if chunk:
                        f.write(chunk)
                        bytes_received += len(chunk)
                        if progress_callback is not None:
                            progress_callback(bytes_received)

            logger.info(
                f"Download complete: {bytes_received} bytes written to {destination}"
            )
            return destination

        except Exception:
            # Remove partial file on any failure
            if destination.exists():
                try:
                    destination.unlink()
                    logger.debug(f"Removed partial file: {destination}")
                except OSError:
                    logger.warning(
                        f"Failed to remove partial file: {destination}"
                    )
            raise

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running or queued backup job.

        Sends a PUT request to /jobs/{jobId}/cancel.

        Args:
            job_id: The unique identifier of the job to cancel.

        Returns:
            True if the cancellation request was successful.

        Raises:
            ConfluenceClientError: If the API request fails (e.g., job not found,
                job already in terminal state, or network error).
        """
        logger.info(f"Cancelling job {job_id}")
        self.client._make_request("PUT", f"jobs/{job_id}/cancel")
        return True

    def clear_queue(self) -> bool:
        """Cancel all queued backup jobs.

        Sends a PUT request to /jobs/clear-queue.

        Returns:
            True if the clear-queue request was successful.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        logger.info("Clearing job queue")
        self.client._make_request("PUT", "jobs/clear-queue")
        return True

    def list_jobs(
        self,
        owner: Optional[str] = None,
        space_key: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        job_states: Optional[List[str]] = None,
        job_operation: Optional[str] = None,
        job_scope: Optional[str] = None,
        limit: int = 50,
    ) -> List[ConfluenceJobDetails]:
        """List backup jobs with optional filters.

        Sends a GET request to /jobs with the specified filter parameters.

        Args:
            owner: Filter by job owner username.
            space_key: Filter by space key.
            from_date: Filter jobs created on or after this date (YYYY-MM-DD).
            to_date: Filter jobs created on or before this date (YYYY-MM-DD).
            job_states: Filter by one or more job states (e.g., ["COMPLETED", "FAILED"]).
            job_operation: Filter by operation type ("BACKUP").
            job_scope: Filter by scope ("SITE" or "SPACE").
            limit: Maximum number of results to return (1–100, default 50).

        Returns:
            List of ConfluenceJobDetails matching the specified filters.

        Raises:
            ValueError: If any filter parameter is invalid (from_date > to_date,
                limit outside [1, 100], or unrecognized enum values).
            ConfluenceClientError: If the API request fails.
        """
        # Validate limit
        if limit < 1 or limit > 100:
            raise ValueError(
                f"limit must be between 1 and 100, got {limit}"
            )

        # Validate job_states
        valid_states = {s.value for s in ConfluenceJobState}
        if job_states is not None:
            for state in job_states:
                if state not in valid_states:
                    raise ValueError(
                        f"Invalid job state: {state!r}. "
                        f"Valid values: {sorted(valid_states)}"
                    )

        # Validate job_operation
        valid_operations = {op.value for op in ConfluenceJobOperation}
        if job_operation is not None:
            if job_operation not in valid_operations:
                raise ValueError(
                    f"Invalid job operation: {job_operation!r}. "
                    f"Valid values: {sorted(valid_operations)}"
                )

        # Validate job_scope
        valid_scopes = {s.value for s in ConfluenceJobScope}
        if job_scope is not None:
            if job_scope not in valid_scopes:
                raise ValueError(
                    f"Invalid job scope: {job_scope!r}. "
                    f"Valid values: {sorted(valid_scopes)}"
                )

        # Validate date range
        if from_date is not None and to_date is not None:
            if from_date > to_date:
                raise ValueError(
                    f"from_date ({from_date}) must not be after "
                    f"to_date ({to_date})"
                )

        # Build query parameters
        params = {"limit": limit}
        if owner is not None:
            params["owner"] = owner
        if space_key is not None:
            params["spaceKey"] = space_key
        if from_date is not None:
            params["fromDate"] = from_date
        if to_date is not None:
            params["toDate"] = to_date
        if job_states is not None:
            params["jobStates"] = ",".join(job_states)
        if job_operation is not None:
            params["jobOperation"] = job_operation
        if job_scope is not None:
            params["jobScope"] = job_scope

        logger.info(f"Listing jobs with filters: {params}")

        response = self.client._make_request("GET", "jobs", params=params)
        data = response.json()

        # Handle both list response and paginated response formats
        if isinstance(data, list):
            return [parse_job_details(item) for item in data]
        elif isinstance(data, dict) and "results" in data:
            return [parse_job_details(item) for item in data["results"]]
        else:
            return [parse_job_details(item) for item in data]

    def get_job_status(self, job_id: str) -> ConfluenceJobDetails:
        """Get the current status of a backup job.

        Sends a GET request to /jobs/{jobId} and returns the parsed Job_Details.

        Args:
            job_id: The unique identifier of the job to query.

        Returns:
            ConfluenceJobDetails with the current job state and details.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        logger.debug(f"Getting job status for job_id={job_id}")
        response = self.client._make_request("GET", f"jobs/{job_id}")
        return parse_job_details(response.json())

    def poll_job(
        self,
        job_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_duration: float = MAX_POLL_DURATION,
        progress_callback: Optional[Callable[[ConfluenceJobDetails], None]] = None,
    ) -> ConfluenceJobDetails:
        """Poll a job until it reaches a terminal state, with retries and timeout.

        Repeatedly checks job status at the configured poll_interval until the job
        reaches a terminal state (COMPLETED, FAILED, or CANCELLED) or the
        max_duration is exceeded.

        Args:
            job_id: The unique identifier of the job to poll.
            poll_interval: Seconds between status checks (clamped to [1, 300]).
                Defaults to DEFAULT_POLL_INTERVAL (5 seconds).
            max_duration: Maximum total polling duration in seconds.
                Defaults to MAX_POLL_DURATION (4 hours).
            progress_callback: Optional callable invoked with the current
                ConfluenceJobDetails on each poll cycle.

        Returns:
            ConfluenceJobDetails when the job reaches COMPLETED state.

        Raises:
            ConfluenceAPIError: If the job reaches FAILED state (with errorMessage)
                or CANCELLED state (with cancelledBy info).
            TimeoutError: If max_duration is exceeded before reaching a terminal state.
            ConfluenceClientError: If network errors exceed MAX_POLL_RETRIES (3)
                consecutive failures.
        """
        # Clamp poll_interval to [1, 300] range
        poll_interval = max(1.0, min(300.0, poll_interval))

        start_time = time.time()
        consecutive_errors = 0
        last_details: Optional[ConfluenceJobDetails] = None

        logger.info(
            f"Starting to poll job {job_id} "
            f"(interval={poll_interval}s, max_duration={max_duration}s)"
        )

        while True:
            elapsed = time.time() - start_time
            if elapsed >= max_duration:
                last_state = (
                    last_details.job_state.value if last_details else "UNKNOWN"
                )
                raise TimeoutError(
                    f"Polling timed out after {elapsed:.1f} seconds. "
                    f"Last observed state: {last_state}"
                )

            try:
                details = self.get_job_status(job_id)
                consecutive_errors = 0  # Reset on success
                last_details = details
            except ConfluenceClientError as e:
                consecutive_errors += 1
                logger.warning(
                    f"Poll attempt failed ({consecutive_errors}/{self.MAX_POLL_RETRIES}): {e}"
                )
                if consecutive_errors >= self.MAX_POLL_RETRIES:
                    raise
                time.sleep(poll_interval)
                continue

            # Invoke progress callback on each successful poll cycle
            if progress_callback is not None:
                progress_callback(details)

            # Check for terminal states
            if details.job_state == ConfluenceJobState.COMPLETED:
                logger.info(f"Job {job_id} completed successfully")
                return details

            if details.job_state == ConfluenceJobState.FAILED:
                error_msg = details.error_message or "Unknown error"
                raise ConfluenceAPIError(
                    f"Job {job_id} failed: {error_msg}"
                )

            if details.job_state == ConfluenceJobState.CANCELLED:
                cancelled_by = details.cancelled_by or "unknown"
                raise ConfluenceAPIError(
                    f"Job {job_id} was cancelled by {cancelled_by}"
                )

            # Wait before next poll
            time.sleep(poll_interval)
