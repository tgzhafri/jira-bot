"""
Tests for Confluence backup service restore operations and file listing.

Covers:
- restore_site: POST /restore/site with filename and skipReindex
- restore_site_upload: multipart POST /restore/site/upload with file size check
- restore_space: POST /restore/space with filename and skipReindex
- restore_space_upload: multipart POST /restore/space/upload with file size check
- list_restore_files: GET /restore/files with optional jobScope filter
- Filename validation (1–255 characters)
- File size validation (≤ 10 GB)
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import responses

from src.config import AtlassianConfig
from src.models.confluence_models import ConfluenceJobState, ConfluenceJobOperation, ConfluenceJobScope
from src.services.confluence_backup_service import ConfluenceBackupService
from src.services.confluence_client import (
    ConfluenceAPIError,
    ConfluenceAuthenticationError,
    ConfluenceClient,
    ConfluencePermissionError,
)


@pytest.fixture
def config():
    return AtlassianConfig(
        url="https://confluence.example.com",
        username="admin@example.com",
        api_token="test-token-long",
    )


@pytest.fixture
def client(config):
    return ConfluenceClient(config)


@pytest.fixture
def service(client):
    return ConfluenceBackupService(client)


@pytest.fixture
def restore_job_response():
    """Standard restore job response from the API."""
    return {
        "id": "restore-job-123",
        "jobOperation": "RESTORE",
        "jobScope": "SITE",
        "jobState": "QUEUED",
        "owner": "admin",
        "fileName": "site-backup-2024.zip",
    }


@pytest.fixture
def space_restore_job_response():
    """Standard space restore job response from the API."""
    return {
        "id": "restore-job-456",
        "jobOperation": "RESTORE",
        "jobScope": "SPACE",
        "jobState": "QUEUED",
        "owner": "admin",
        "fileName": "space-backup-2024.zip",
    }


BASE_URL = "https://confluence.example.com/rest/api/backup-restore/"


class TestRestoreSite:
    """Tests for restore_site method."""

    @responses.activate
    def test_restore_site_success(self, service, restore_job_response):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site",
            json=restore_job_response,
            status=200,
        )

        result = service.restore_site("site-backup-2024.zip")

        assert result.id == "restore-job-123"
        assert result.job_operation == ConfluenceJobOperation.RESTORE
        assert result.job_scope == ConfluenceJobScope.SITE
        assert result.job_state == ConfluenceJobState.QUEUED

        # Verify request body
        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["filename"] == "site-backup-2024.zip"
        assert request_body["skipReindex"] is False

    @responses.activate
    def test_restore_site_with_skip_reindex(self, service, restore_job_response):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site",
            json=restore_job_response,
            status=200,
        )

        result = service.restore_site("site-backup-2024.zip", skip_reindex=True)

        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["skipReindex"] is True
        assert result.id == "restore-job-123"

    def test_restore_site_empty_filename(self, service):
        with pytest.raises(ValueError, match="filename must be between 1 and 255"):
            service.restore_site("")

    def test_restore_site_filename_too_long(self, service):
        long_name = "a" * 256
        with pytest.raises(ValueError, match="filename must be between 1 and 255"):
            service.restore_site(long_name)

    @responses.activate
    def test_restore_site_filename_max_length(self, service, restore_job_response):
        """Filename of exactly 255 characters should be accepted."""
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site",
            json=restore_job_response,
            status=200,
        )

        filename = "a" * 255
        result = service.restore_site(filename)
        assert result.id == "restore-job-123"

    @responses.activate
    def test_restore_site_api_error(self, service):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site",
            json={"error": "File not found"},
            status=404,
        )

        with pytest.raises(ConfluenceAPIError):
            service.restore_site("nonexistent.zip")


class TestRestoreSiteUpload:
    """Tests for restore_site_upload method."""

    @responses.activate
    def test_restore_site_upload_success(self, service, restore_job_response, tmp_path):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site/upload",
            json=restore_job_response,
            status=200,
        )

        # Create a small test file
        test_file = tmp_path / "site-backup.zip"
        test_file.write_bytes(b"fake backup content")

        result = service.restore_site_upload(test_file)

        assert result.id == "restore-job-123"
        assert result.job_operation == ConfluenceJobOperation.RESTORE
        assert result.job_state == ConfluenceJobState.QUEUED

    @responses.activate
    def test_restore_site_upload_with_skip_reindex(
        self, service, restore_job_response, tmp_path
    ):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site/upload",
            json=restore_job_response,
            status=200,
        )

        test_file = tmp_path / "site-backup.zip"
        test_file.write_bytes(b"fake backup content")

        result = service.restore_site_upload(test_file, skip_reindex=True)
        assert result.id == "restore-job-123"

        # Verify skipReindex was sent in the request body
        request_body = responses.calls[0].request.body.decode("utf-8")
        assert "true" in request_body

    def test_restore_site_upload_file_not_found(self, service, tmp_path):
        nonexistent = tmp_path / "nonexistent.zip"

        with pytest.raises(FileNotFoundError, match="File not found"):
            service.restore_site_upload(nonexistent)

    def test_restore_site_upload_file_too_large(self, service, tmp_path):
        test_file = tmp_path / "large-backup.zip"
        test_file.write_bytes(b"x")  # Create a small file

        # Mock the file size to exceed 10 GB
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 11 * 1024**3  # 11 GB
            with patch.object(Path, "exists", return_value=True):
                with pytest.raises(ValueError, match="exceeds maximum allowed size"):
                    service.restore_site_upload(test_file)

    @responses.activate
    def test_restore_site_upload_auth_error(self, service, tmp_path):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/site/upload",
            json={"error": "Unauthorized"},
            status=401,
        )

        test_file = tmp_path / "site-backup.zip"
        test_file.write_bytes(b"fake backup content")

        with pytest.raises(ConfluenceAuthenticationError):
            service.restore_site_upload(test_file)


class TestRestoreSpace:
    """Tests for restore_space method."""

    @responses.activate
    def test_restore_space_success(self, service, space_restore_job_response):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/space",
            json=space_restore_job_response,
            status=200,
        )

        result = service.restore_space("space-backup-2024.zip")

        assert result.id == "restore-job-456"
        assert result.job_operation == ConfluenceJobOperation.RESTORE
        assert result.job_scope == ConfluenceJobScope.SPACE
        assert result.job_state == ConfluenceJobState.QUEUED

        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["filename"] == "space-backup-2024.zip"
        assert request_body["skipReindex"] is False

    @responses.activate
    def test_restore_space_with_skip_reindex(self, service, space_restore_job_response):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/space",
            json=space_restore_job_response,
            status=200,
        )

        result = service.restore_space("space-backup-2024.zip", skip_reindex=True)

        request_body = json.loads(responses.calls[0].request.body)
        assert request_body["skipReindex"] is True
        assert result.id == "restore-job-456"

    def test_restore_space_empty_filename(self, service):
        with pytest.raises(ValueError, match="filename must be between 1 and 255"):
            service.restore_space("")

    def test_restore_space_filename_too_long(self, service):
        long_name = "b" * 256
        with pytest.raises(ValueError, match="filename must be between 1 and 255"):
            service.restore_space(long_name)

    @responses.activate
    def test_restore_space_api_error(self, service):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/space",
            json={"error": "Internal error"},
            status=500,
        )

        with pytest.raises(ConfluenceAPIError):
            service.restore_space("backup.zip")


class TestRestoreSpaceUpload:
    """Tests for restore_space_upload method."""

    @responses.activate
    def test_restore_space_upload_success(
        self, service, space_restore_job_response, tmp_path
    ):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/space/upload",
            json=space_restore_job_response,
            status=200,
        )

        test_file = tmp_path / "space-backup.zip"
        test_file.write_bytes(b"fake space backup content")

        result = service.restore_space_upload(test_file)

        assert result.id == "restore-job-456"
        assert result.job_operation == ConfluenceJobOperation.RESTORE
        assert result.job_scope == ConfluenceJobScope.SPACE

    @responses.activate
    def test_restore_space_upload_with_skip_reindex(
        self, service, space_restore_job_response, tmp_path
    ):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/space/upload",
            json=space_restore_job_response,
            status=200,
        )

        test_file = tmp_path / "space-backup.zip"
        test_file.write_bytes(b"fake space backup content")

        result = service.restore_space_upload(test_file, skip_reindex=True)
        assert result.id == "restore-job-456"

    def test_restore_space_upload_file_not_found(self, service, tmp_path):
        nonexistent = tmp_path / "nonexistent.zip"

        with pytest.raises(FileNotFoundError, match="File not found"):
            service.restore_space_upload(nonexistent)

    def test_restore_space_upload_file_too_large(self, service, tmp_path):
        test_file = tmp_path / "large-space-backup.zip"
        test_file.write_bytes(b"x")

        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 11 * 1024**3
            with patch.object(Path, "exists", return_value=True):
                with pytest.raises(ValueError, match="exceeds maximum allowed size"):
                    service.restore_space_upload(test_file)

    @responses.activate
    def test_restore_space_upload_permission_error(self, service, tmp_path):
        responses.add(
            responses.POST,
            f"{BASE_URL}restore/space/upload",
            json={"error": "Forbidden"},
            status=403,
        )

        test_file = tmp_path / "space-backup.zip"
        test_file.write_bytes(b"fake space backup content")

        with pytest.raises(ConfluencePermissionError):
            service.restore_space_upload(test_file)


class TestListRestoreFiles:
    """Tests for list_restore_files method."""

    @responses.activate
    def test_list_restore_files_no_filter(self, service):
        file_list = ["site-backup-2024.zip", "space-backup-DEV.zip", "old-backup.zip"]
        responses.add(
            responses.GET,
            f"{BASE_URL}restore/files",
            json=file_list,
            status=200,
        )

        result = service.list_restore_files()

        assert result == file_list
        assert len(result) == 3

    @responses.activate
    def test_list_restore_files_with_site_scope(self, service):
        file_list = ["site-backup-2024.zip"]
        responses.add(
            responses.GET,
            f"{BASE_URL}restore/files",
            json=file_list,
            status=200,
        )

        result = service.list_restore_files(job_scope="SITE")

        assert result == file_list
        # Verify query parameter was sent
        assert "jobScope=SITE" in responses.calls[0].request.url

    @responses.activate
    def test_list_restore_files_with_space_scope(self, service):
        file_list = ["space-backup-DEV.zip", "space-backup-QA.zip"]
        responses.add(
            responses.GET,
            f"{BASE_URL}restore/files",
            json=file_list,
            status=200,
        )

        result = service.list_restore_files(job_scope="SPACE")

        assert result == file_list
        assert "jobScope=SPACE" in responses.calls[0].request.url

    @responses.activate
    def test_list_restore_files_empty_result(self, service):
        responses.add(
            responses.GET,
            f"{BASE_URL}restore/files",
            json=[],
            status=200,
        )

        result = service.list_restore_files()

        assert result == []

    @responses.activate
    def test_list_restore_files_api_error(self, service):
        responses.add(
            responses.GET,
            f"{BASE_URL}restore/files",
            json={"error": "Server error"},
            status=500,
        )

        with pytest.raises(ConfluenceAPIError):
            service.list_restore_files()


class TestFilenameValidation:
    """Tests for filename validation helper."""

    def test_validate_filename_single_char(self, service):
        """Single character filename should be valid."""
        # Should not raise
        service._validate_filename("a")

    def test_validate_filename_255_chars(self, service):
        """255 character filename should be valid."""
        service._validate_filename("x" * 255)

    def test_validate_filename_empty(self, service):
        with pytest.raises(ValueError):
            service._validate_filename("")

    def test_validate_filename_256_chars(self, service):
        with pytest.raises(ValueError):
            service._validate_filename("x" * 256)
