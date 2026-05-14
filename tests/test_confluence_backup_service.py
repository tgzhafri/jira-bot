"""
Tests for ConfluenceBackupService job polling and status methods.
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import responses

from src.config import AtlassianConfig
from src.models.confluence_models import (
    ConfluenceJobDetails,
    ConfluenceJobOperation,
    ConfluenceJobScope,
    ConfluenceJobState,
)
from src.services.confluence_backup_service import ConfluenceBackupService
from src.services.confluence_client import (
    ConfluenceAPIError,
    ConfluenceClient,
    ConfluenceConnectionError,
)


@pytest.fixture
def config():
    """Create a test AtlassianConfig."""
    return AtlassianConfig(
        url="https://confluence.example.com",
        username="admin@example.com",
        api_token="test-token-long",
    )


@pytest.fixture
def client(config):
    """Create a test ConfluenceClient."""
    return ConfluenceClient(config)


@pytest.fixture
def service(client):
    """Create a test ConfluenceBackupService."""
    return ConfluenceBackupService(client)


def _make_job_response(
    job_id="job-123",
    state="IN_PROGRESS",
    operation="BACKUP",
    scope="SITE",
    error_message=None,
    cancelled_by=None,
):
    """Helper to create a job status API response dict."""
    resp = {
        "id": job_id,
        "jobOperation": operation,
        "jobScope": scope,
        "jobState": state,
    }
    if error_message:
        resp["errorMessage"] = error_message
    if cancelled_by:
        resp["cancelledBy"] = cancelled_by
    return resp


class TestGetJobStatus:
    """Tests for get_job_status method."""

    @responses.activate
    def test_get_job_status_success(self, service):
        """Test successful job status retrieval."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="IN_PROGRESS"),
            status=200,
        )

        result = service.get_job_status("job-123")

        assert isinstance(result, ConfluenceJobDetails)
        assert result.id == "job-123"
        assert result.job_state == ConfluenceJobState.IN_PROGRESS

    @responses.activate
    def test_get_job_status_completed(self, service):
        """Test job status retrieval for completed job."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-456",
            json=_make_job_response(job_id="job-456", state="COMPLETED"),
            status=200,
        )

        result = service.get_job_status("job-456")

        assert result.job_state == ConfluenceJobState.COMPLETED
        assert result.is_terminal is True

    @responses.activate
    def test_get_job_status_api_error(self, service):
        """Test job status retrieval with API error."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/bad-id",
            json={"error": "Not found"},
            status=404,
        )

        with pytest.raises(ConfluenceAPIError):
            service.get_job_status("bad-id")


class TestPollJob:
    """Tests for poll_job method."""

    @responses.activate
    def test_poll_job_immediate_completion(self, service):
        """Test polling a job that is already completed."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="COMPLETED"),
            status=200,
        )

        result = service.poll_job("job-123", poll_interval=1, max_duration=10)

        assert result.job_state == ConfluenceJobState.COMPLETED

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_transitions_to_completed(self, mock_sleep, service):
        """Test polling through state transitions until completion."""
        # First poll: IN_PROGRESS
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="IN_PROGRESS"),
            status=200,
        )
        # Second poll: COMPLETED
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="COMPLETED"),
            status=200,
        )

        result = service.poll_job("job-123", poll_interval=1, max_duration=60)

        assert result.job_state == ConfluenceJobState.COMPLETED
        mock_sleep.assert_called_once_with(1.0)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_failed_raises_error(self, mock_sleep, service):
        """Test that FAILED state raises ConfluenceAPIError with errorMessage."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(
                state="FAILED", error_message="Disk space exhausted"
            ),
            status=200,
        )

        with pytest.raises(ConfluenceAPIError, match="Disk space exhausted"):
            service.poll_job("job-123", poll_interval=1, max_duration=60)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_cancelled_raises_error(self, mock_sleep, service):
        """Test that CANCELLED state raises ConfluenceAPIError with cancelledBy."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="CANCELLED", cancelled_by="admin_user"),
            status=200,
        )

        with pytest.raises(ConfluenceAPIError, match="admin_user"):
            service.poll_job("job-123", poll_interval=1, max_duration=60)

    @patch("src.services.confluence_backup_service.time.time")
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_timeout(self, mock_sleep, mock_time, service):
        """Test that TimeoutError is raised when max_duration is exceeded."""
        # Simulate time progression: start=0, first check ok (elapsed=0), second check exceeds
        mock_time.side_effect = [0, 0, 100]

        def mock_get_status(job_id):
            return ConfluenceJobDetails(
                id="job-123",
                job_operation=ConfluenceJobOperation.BACKUP,
                job_scope=ConfluenceJobScope.SITE,
                job_state=ConfluenceJobState.IN_PROGRESS,
            )

        with patch.object(service, "get_job_status", side_effect=mock_get_status):
            with pytest.raises(TimeoutError, match="timed out"):
                service.poll_job("job-123", poll_interval=1, max_duration=10)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_progress_callback_invoked(self, mock_sleep, service):
        """Test that progress_callback is invoked on each poll cycle."""
        # First poll: QUEUED
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="QUEUED"),
            status=200,
        )
        # Second poll: IN_PROGRESS
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="IN_PROGRESS"),
            status=200,
        )
        # Third poll: COMPLETED
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="COMPLETED"),
            status=200,
        )

        callback = MagicMock()
        result = service.poll_job(
            "job-123", poll_interval=1, max_duration=60, progress_callback=callback
        )

        assert result.job_state == ConfluenceJobState.COMPLETED
        assert callback.call_count == 3
        # Verify callback received ConfluenceJobDetails
        for call in callback.call_args_list:
            assert isinstance(call[0][0], ConfluenceJobDetails)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_retries_on_network_error(self, mock_sleep, service):
        """Test that transient network errors are retried up to MAX_POLL_RETRIES."""
        # First poll: network error
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            body=ConnectionError("Network unreachable"),
        )
        # Second poll: network error
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            body=ConnectionError("Network unreachable"),
        )
        # Third poll: success (COMPLETED)
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="COMPLETED"),
            status=200,
        )

        result = service.poll_job("job-123", poll_interval=1, max_duration=60)

        assert result.job_state == ConfluenceJobState.COMPLETED
        # Sleep called twice for the two retries
        assert mock_sleep.call_count == 2

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_raises_after_max_retries(self, mock_sleep, service):
        """Test that error is raised after MAX_POLL_RETRIES consecutive failures."""
        # Three consecutive network errors
        for _ in range(3):
            responses.add(
                responses.GET,
                "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
                body=ConnectionError("Network unreachable"),
            )

        with pytest.raises(ConfluenceConnectionError):
            service.poll_job("job-123", poll_interval=1, max_duration=60)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_resets_error_count_on_success(self, mock_sleep, service):
        """Test that consecutive error count resets after a successful poll."""
        # Two errors, then success, then two more errors, then success (COMPLETED)
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            body=ConnectionError("Network unreachable"),
        )
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            body=ConnectionError("Network unreachable"),
        )
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="IN_PROGRESS"),
            status=200,
        )
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            body=ConnectionError("Network unreachable"),
        )
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            body=ConnectionError("Network unreachable"),
        )
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="COMPLETED"),
            status=200,
        )

        result = service.poll_job("job-123", poll_interval=1, max_duration=60)

        assert result.job_state == ConfluenceJobState.COMPLETED

    def test_poll_job_clamps_interval_minimum(self, service):
        """Test that poll_interval is clamped to minimum of 1 second."""
        with patch.object(service, "get_job_status") as mock_get:
            mock_get.return_value = ConfluenceJobDetails(
                id="job-123",
                job_operation=ConfluenceJobOperation.BACKUP,
                job_scope=ConfluenceJobScope.SITE,
                job_state=ConfluenceJobState.COMPLETED,
            )

            result = service.poll_job("job-123", poll_interval=0.1, max_duration=60)

            assert result.job_state == ConfluenceJobState.COMPLETED

    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_clamps_interval_maximum(self, mock_sleep, service):
        """Test that poll_interval is clamped to maximum of 300 seconds."""
        call_count = [0]

        def mock_get_status(job_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return ConfluenceJobDetails(
                    id="job-123",
                    job_operation=ConfluenceJobOperation.BACKUP,
                    job_scope=ConfluenceJobScope.SITE,
                    job_state=ConfluenceJobState.IN_PROGRESS,
                )
            return ConfluenceJobDetails(
                id="job-123",
                job_operation=ConfluenceJobOperation.BACKUP,
                job_scope=ConfluenceJobScope.SITE,
                job_state=ConfluenceJobState.COMPLETED,
            )

        with patch.object(service, "get_job_status", side_effect=mock_get_status):
            result = service.poll_job("job-123", poll_interval=500, max_duration=600)

        assert result.job_state == ConfluenceJobState.COMPLETED
        # Verify sleep was called with clamped value of 300
        mock_sleep.assert_called_once_with(300.0)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_default_interval(self, mock_sleep, service):
        """Test that default poll_interval is 5 seconds."""
        # First poll: IN_PROGRESS
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="IN_PROGRESS"),
            status=200,
        )
        # Second poll: COMPLETED
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="COMPLETED"),
            status=200,
        )

        service.poll_job("job-123", max_duration=60)

        mock_sleep.assert_called_once_with(5.0)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_failed_without_error_message(self, mock_sleep, service):
        """Test FAILED state with no errorMessage uses default message."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="FAILED"),
            status=200,
        )

        with pytest.raises(ConfluenceAPIError, match="Unknown error"):
            service.poll_job("job-123", poll_interval=1, max_duration=60)

    @responses.activate
    @patch("src.services.confluence_backup_service.time.sleep")
    def test_poll_job_cancelled_without_cancelled_by(self, mock_sleep, service):
        """Test CANCELLED state with no cancelledBy uses 'unknown'."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123",
            json=_make_job_response(state="CANCELLED"),
            status=200,
        )

        with pytest.raises(ConfluenceAPIError, match="unknown"):
            service.poll_job("job-123", poll_interval=1, max_duration=60)


class TestDownloadBackup:
    """Tests for download_backup method."""

    @responses.activate
    def test_download_backup_success(self, service, tmp_path):
        """Test successful backup download with streaming."""
        content = b"backup file content " * 100  # ~2000 bytes
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123/download",
            body=content,
            status=200,
            stream=True,
        )

        destination = tmp_path / "backups" / "test_backup.zip"
        result = service.download_backup("job-123", destination)

        assert result == destination
        assert destination.exists()
        assert destination.read_bytes() == content

    @responses.activate
    def test_download_backup_creates_parent_dirs(self, service, tmp_path):
        """Test that parent directories are created if they don't exist."""
        content = b"data"
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123/download",
            body=content,
            status=200,
            stream=True,
        )

        destination = tmp_path / "deep" / "nested" / "dir" / "backup.zip"
        service.download_backup("job-123", destination)

        assert destination.exists()
        assert destination.read_bytes() == content

    @responses.activate
    def test_download_backup_progress_callback(self, service, tmp_path):
        """Test that progress callback is invoked with cumulative bytes."""
        # Create content larger than chunk size (8192 bytes)
        content = b"x" * (8192 * 3 + 100)
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123/download",
            body=content,
            status=200,
            stream=True,
        )

        destination = tmp_path / "backup.zip"
        callback = MagicMock()
        service.download_backup("job-123", destination, progress_callback=callback)

        assert callback.called
        # Final call should report total bytes
        final_bytes = callback.call_args_list[-1][0][0]
        assert final_bytes == len(content)
        # Verify monotonically increasing
        reported_bytes = [call[0][0] for call in callback.call_args_list]
        assert reported_bytes == sorted(reported_bytes)

    @responses.activate
    def test_download_backup_removes_partial_on_api_error(self, service, tmp_path):
        """Test that partial file is removed on API error."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123/download",
            json={"error": "Not found"},
            status=404,
        )

        destination = tmp_path / "backup.zip"
        with pytest.raises(ConfluenceAPIError):
            service.download_backup("job-123", destination)

        assert not destination.exists()

    @responses.activate
    def test_download_backup_no_callback(self, service, tmp_path):
        """Test download works without progress callback."""
        content = b"simple content"
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123/download",
            body=content,
            status=200,
            stream=True,
        )

        destination = tmp_path / "backup.zip"
        result = service.download_backup("job-123", destination)

        assert result == destination
        assert destination.read_bytes() == content


class TestCancelJob:
    """Tests for cancel_job method."""

    @responses.activate
    def test_cancel_job_success(self, service):
        """Test successful job cancellation."""
        responses.add(
            responses.PUT,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-123/cancel",
            status=200,
        )

        result = service.cancel_job("job-123")

        assert result is True

    @responses.activate
    def test_cancel_job_not_found(self, service):
        """Test cancellation of non-existent job raises error."""
        responses.add(
            responses.PUT,
            "https://confluence.example.com/rest/api/backup-restore/jobs/bad-id/cancel",
            json={"error": "Job not found"},
            status=404,
        )

        with pytest.raises(ConfluenceAPIError):
            service.cancel_job("bad-id")

    @responses.activate
    def test_cancel_job_already_terminal(self, service):
        """Test cancellation of already-completed job raises error."""
        responses.add(
            responses.PUT,
            "https://confluence.example.com/rest/api/backup-restore/jobs/job-done/cancel",
            json={"error": "Job already completed"},
            status=409,
        )

        with pytest.raises(ConfluenceAPIError):
            service.cancel_job("job-done")


class TestClearQueue:
    """Tests for clear_queue method."""

    @responses.activate
    def test_clear_queue_success(self, service):
        """Test successful queue clearing."""
        responses.add(
            responses.PUT,
            "https://confluence.example.com/rest/api/backup-restore/jobs/clear-queue",
            status=200,
        )

        result = service.clear_queue()

        assert result is True

    @responses.activate
    def test_clear_queue_api_error(self, service):
        """Test clear queue with API error."""
        responses.add(
            responses.PUT,
            "https://confluence.example.com/rest/api/backup-restore/jobs/clear-queue",
            json={"error": "Internal error"},
            status=500,
        )

        with pytest.raises(ConfluenceAPIError):
            service.clear_queue()


class TestListJobs:
    """Tests for list_jobs method."""

    @responses.activate
    def test_list_jobs_no_filters(self, service):
        """Test listing jobs with no filters returns results."""
        job_list = [
            _make_job_response(job_id="job-1", state="COMPLETED"),
            _make_job_response(job_id="job-2", state="IN_PROGRESS"),
        ]
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs",
            json=job_list,
            status=200,
        )

        result = service.list_jobs()

        assert len(result) == 2
        assert result[0].id == "job-1"
        assert result[1].id == "job-2"

    @responses.activate
    def test_list_jobs_with_filters(self, service):
        """Test listing jobs with various filters."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs",
            json=[_make_job_response(job_id="job-1", state="COMPLETED")],
            status=200,
        )

        result = service.list_jobs(
            owner="admin",
            space_key="DEV",
            from_date="2024-01-01",
            to_date="2024-12-31",
            job_states=["COMPLETED"],
            job_operation="BACKUP",
            job_scope="SITE",
            limit=10,
        )

        assert len(result) == 1
        # Verify query params were sent
        request = responses.calls[0].request
        assert "owner=admin" in request.url
        assert "spaceKey=DEV" in request.url
        assert "fromDate=2024-01-01" in request.url
        assert "toDate=2024-12-31" in request.url
        assert "jobStates=COMPLETED" in request.url
        assert "jobOperation=BACKUP" in request.url
        assert "jobScope=SITE" in request.url
        assert "limit=10" in request.url

    @responses.activate
    def test_list_jobs_empty_result(self, service):
        """Test listing jobs with no matches returns empty list."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs",
            json=[],
            status=200,
        )

        result = service.list_jobs(owner="nobody")

        assert result == []

    @responses.activate
    def test_list_jobs_paginated_response(self, service):
        """Test listing jobs with paginated response format."""
        responses.add(
            responses.GET,
            "https://confluence.example.com/rest/api/backup-restore/jobs",
            json={"results": [_make_job_response(job_id="job-1", state="QUEUED")]},
            status=200,
        )

        result = service.list_jobs()

        assert len(result) == 1
        assert result[0].id == "job-1"

    def test_list_jobs_invalid_limit_too_low(self, service):
        """Test that limit < 1 raises ValueError."""
        with pytest.raises(ValueError, match="limit must be between 1 and 100"):
            service.list_jobs(limit=0)

    def test_list_jobs_invalid_limit_too_high(self, service):
        """Test that limit > 100 raises ValueError."""
        with pytest.raises(ValueError, match="limit must be between 1 and 100"):
            service.list_jobs(limit=101)

    def test_list_jobs_invalid_job_state(self, service):
        """Test that invalid job state raises ValueError."""
        with pytest.raises(ValueError, match="Invalid job state"):
            service.list_jobs(job_states=["INVALID_STATE"])

    def test_list_jobs_invalid_job_operation(self, service):
        """Test that invalid job operation raises ValueError."""
        with pytest.raises(ValueError, match="Invalid job operation"):
            service.list_jobs(job_operation="INVALID")

    def test_list_jobs_invalid_job_scope(self, service):
        """Test that invalid job scope raises ValueError."""
        with pytest.raises(ValueError, match="Invalid job scope"):
            service.list_jobs(job_scope="INVALID")

    def test_list_jobs_from_date_after_to_date(self, service):
        """Test that from_date > to_date raises ValueError."""
        with pytest.raises(ValueError, match="from_date.*must not be after.*to_date"):
            service.list_jobs(from_date="2024-12-31", to_date="2024-01-01")

    def test_list_jobs_valid_date_range(self, service):
        """Test that from_date == to_date is valid."""
        # Should not raise - equal dates are valid
        # We need to mock the HTTP call
        with patch.object(service.client, "_make_request") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_req.return_value = mock_response

            result = service.list_jobs(from_date="2024-06-15", to_date="2024-06-15")

            assert result == []

    def test_list_jobs_default_limit(self, service):
        """Test that default limit is 50."""
        with patch.object(service.client, "_make_request") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_req.return_value = mock_response

            service.list_jobs()

            # Verify limit=50 was passed in params
            call_kwargs = mock_req.call_args
            params = call_kwargs[1].get("params") or call_kwargs[0][2] if len(call_kwargs[0]) > 2 else call_kwargs[1].get("params")
            assert params["limit"] == 50

    def test_list_jobs_multiple_job_states(self, service):
        """Test that multiple job states are joined with comma."""
        with patch.object(service.client, "_make_request") as mock_req:
            mock_response = MagicMock()
            mock_response.json.return_value = []
            mock_req.return_value = mock_response

            service.list_jobs(job_states=["COMPLETED", "FAILED"])

            call_kwargs = mock_req.call_args
            params = call_kwargs[1].get("params") or call_kwargs[0][2] if len(call_kwargs[0]) > 2 else call_kwargs[1].get("params")
            assert params["jobStates"] == "COMPLETED,FAILED"
