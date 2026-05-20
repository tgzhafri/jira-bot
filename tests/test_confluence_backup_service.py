"""
Tests for Confluence Cloud backup service.

Tests the ConfluenceBackupService which exports pages in storage format
and downloads attachments from Confluence Cloud.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import AtlassianConfig
from src.models.confluence_models import BackupAttachment, BackupPage, SpaceBackupResult
from src.services.confluence_backup_service import ConfluenceBackupService
from src.services.confluence_client import ConfluenceClientError, ConfluenceCloudClient


@pytest.fixture
def config():
    """Create a test AtlassianConfig."""
    return AtlassianConfig(
        url="https://test.atlassian.net",
        username="admin@example.com",
        api_token="test-token-long-enough",
    )


@pytest.fixture
def mock_client(config):
    """Create a mocked ConfluenceCloudClient."""
    with patch.object(ConfluenceCloudClient, "__init__", return_value=None):
        client = ConfluenceCloudClient.__new__(ConfluenceCloudClient)
        client.config = config
        client._confluence = MagicMock()
    return client


@pytest.fixture
def service(mock_client, tmp_path):
    """Create a ConfluenceBackupService with a temp output directory."""
    return ConfluenceBackupService(client=mock_client, output_dir=tmp_path)


def _make_page_response(page_id="123", title="Test Page", body="<p>Hello</p>"):
    """Helper to create a page API response dict."""
    return {
        "id": page_id,
        "title": title,
        "body": {"storage": {"value": body}},
        "version": {"number": 1},
        "ancestors": [],
    }


def _make_attachment_response(att_id="att-1", title="file.png", size=1024):
    """Helper to create an attachment API response dict."""
    return {
        "id": att_id,
        "title": title,
        "extensions": {
            "mediaType": "image/png",
            "fileSize": size,
        },
        "_links": {
            "download": f"/wiki/rest/api/content/{att_id}/download",
        },
    }


class TestBackupPage:
    """Tests for BackupPage model."""

    def test_from_api_response_basic(self):
        """Test parsing a basic page response."""
        data = _make_page_response(page_id="42", title="My Page", body="<p>Content</p>")
        page = BackupPage.from_api_response(data, "DEV")

        assert page.id == "42"
        assert page.title == "My Page"
        assert page.space_key == "DEV"
        assert page.storage_body == "<p>Content</p>"
        assert page.version_number == 1
        assert page.parent_id is None
        assert page.ancestors == []

    def test_from_api_response_with_ancestors(self):
        """Test parsing a page with ancestors."""
        data = _make_page_response()
        data["ancestors"] = [{"id": "10"}, {"id": "20"}]
        page = BackupPage.from_api_response(data, "HR")

        assert page.ancestors == ["10", "20"]
        assert page.parent_id == "20"

    def test_to_dict_roundtrip(self):
        """Test serialization to dict."""
        page = BackupPage(
            id="1",
            title="Test",
            space_key="DEV",
            storage_body="<p>Hi</p>",
            version_number=3,
            parent_id="0",
            ancestors=["0"],
        )
        d = page.to_dict()

        assert d["id"] == "1"
        assert d["storageBody"] == "<p>Hi</p>"
        assert d["versionNumber"] == 3


class TestBackupAttachment:
    """Tests for BackupAttachment model."""

    def test_from_api_response(self):
        """Test parsing an attachment response."""
        data = _make_attachment_response(att_id="a1", title="doc.pdf", size=2048)
        att = BackupAttachment.from_api_response(data)

        assert att.id == "a1"
        assert att.file_name == "doc.pdf"
        assert att.media_type == "application/pdf" or att.media_type == "image/png"
        assert att.file_size == 2048


class TestBackupSpace:
    """Tests for ConfluenceBackupService.backup_space."""

    def test_backup_space_success(self, service, mock_client, tmp_path):
        """Test successful space backup with pages and no attachments."""
        pages = [
            _make_page_response("1", "Page One", "<p>One</p>"),
            _make_page_response("2", "Page Two", "<p>Two</p>"),
        ]
        mock_client.get_all_pages_from_space_generator = MagicMock(return_value=iter(pages))
        mock_client.get_attachments_from_page = MagicMock(return_value=[])

        result = service.backup_space("DEV", include_attachments=False)

        assert isinstance(result, SpaceBackupResult)
        assert result.space_key == "DEV"
        assert result.total_pages == 2
        assert result.total_attachments == 0
        assert not result.has_errors

        # Verify files were created
        backup_dir = Path(result.backup_path)
        assert (backup_dir / "metadata.json").exists()
        assert (backup_dir / "pages" / "1.json").exists()
        assert (backup_dir / "pages" / "2.json").exists()

    def test_backup_space_with_attachments(self, service, mock_client, tmp_path):
        """Test backup with attachment downloads."""
        pages = [_make_page_response("1", "Page One", "<p>One</p>")]
        mock_client.get_all_pages_from_space_generator = MagicMock(return_value=iter(pages))
        mock_client.get_attachments_from_page = MagicMock(
            return_value=[_make_attachment_response("att-1", "image.png", 512)]
        )
        mock_client.download_attachments_from_page = MagicMock(
            return_value={"image.png": b"fake-png-data"}
        )

        result = service.backup_space("DEV", include_attachments=True)

        assert result.total_attachments == 1
        mock_client.download_attachments_from_page.assert_called_once_with("1")

        # Verify attachment file was saved
        backup_dir = Path(result.backup_path)
        att_file = backup_dir / "attachments" / "1" / "image.png"
        assert att_file.exists()
        assert att_file.read_bytes() == b"fake-png-data"

    def test_backup_space_handles_page_fetch_error(self, service, mock_client):
        """Test that a failed page fetch returns an error result."""
            side_effect=ConfluenceClientError("API timeout")
        )
        mock_client.get_all_pages_from_space_generator = MagicMock(
            side_effect=ConfluenceClientError("API timeout")
        )

        result = service.backup_space("BROKEN")

        assert result.total_pages == 0
        assert result.has_errors
        assert "API timeout" in result.errors[0]

    def test_backup_space_handles_attachment_download_error(
        self, service, mock_client, tmp_path
    ):
        """Test that attachment download errors are recorded but don't stop backup."""
        pages = [_make_page_response("1", "Page", "<p>X</p>")]
        mock_client.get_all_pages_from_space_generator = MagicMock(return_value=iter(pages))
        mock_client.get_attachments_from_page = MagicMock(
            return_value=[_make_attachment_response("att-1", "big.zip", 999)]
        )
        mock_client.download_attachments_from_page = MagicMock(
            side_effect=ConfluenceClientError("Download failed")
        )

        result = service.backup_space("DEV", include_attachments=True)

        # Page should still be saved
        assert result.total_pages == 1
        assert result.total_attachments == 0
        assert result.has_errors
        assert "Download failed" in result.errors[0]

    def test_backup_space_progress_callback(self, service, mock_client):
        """Test that progress callback is invoked during backup."""
        pages = [
            _make_page_response("1", "P1", "<p>1</p>"),
            _make_page_response("2", "P2", "<p>2</p>"),
        ]
        mock_client.get_all_pages_from_space_generator = MagicMock(return_value=iter(pages))
        mock_client.get_attachments_from_page = MagicMock(return_value=[])

        callback = MagicMock()
        service.backup_space("DEV", include_attachments=False, progress_callback=callback)

        assert callback.called
        # Should be called at least for "Fetching page list" + once per page
        assert callback.call_count >= 3

    def test_backup_space_metadata_file(self, service, mock_client, tmp_path):
        """Test that metadata.json contains correct information."""
        pages = [_make_page_response("1", "Page", "<p>X</p>")]
        mock_client.get_all_pages_from_space_generator = MagicMock(return_value=iter(pages))
        mock_client.get_attachments_from_page = MagicMock(return_value=[])

        result = service.backup_space("TEST", include_attachments=False)

        metadata_path = Path(result.backup_path) / "metadata.json"
        metadata = json.loads(metadata_path.read_text())

        assert metadata["spaceKey"] == "TEST"
        assert metadata["totalPages"] == 1
        assert metadata["format"] == "storage"
        assert "backupTimestamp" in metadata


class TestBackupSpaces:
    """Tests for ConfluenceBackupService.backup_spaces."""

    def test_backup_multiple_spaces(self, service, mock_client):
        """Test backing up multiple spaces."""
        pages = [_make_page_response("1", "P", "<p>X</p>")]
        mock_client.get_all_pages_from_space_generator = MagicMock(side_effect=lambda *a, **kw: iter(pages))
        mock_client.get_attachments_from_page = MagicMock(return_value=[])

        results = service.backup_spaces(["DEV", "HR"], include_attachments=False)

        assert len(results) == 2
        assert results[0].space_key == "DEV"
        assert results[1].space_key == "HR"


class TestCreateZipBackup:
    """Tests for ConfluenceBackupService.create_zip_backup."""

    def test_create_zip_backup_success(self, service, mock_client, tmp_path):
        """Test that ZIP backup creates a zip file and removes the directory."""
        pages = [_make_page_response("1", "Page", "<p>X</p>")]
        mock_client.get_all_pages_from_space_generator = MagicMock(return_value=iter(pages))
        mock_client.get_attachments_from_page = MagicMock(return_value=[])

        zip_path = service.create_zip_backup("DEV", include_attachments=False)

        assert zip_path is not None
        assert zip_path.endswith(".zip")
        assert os.path.exists(zip_path)
        # Clean up temp file
        os.remove(zip_path)

    def test_create_zip_backup_failure_returns_none(self, service, mock_client):
        """Test that total failure returns None."""
            side_effect=ConfluenceClientError("Network error")
        )
        mock_client.get_all_pages_from_space_generator = MagicMock(
            side_effect=ConfluenceClientError("Network error")
        )

        result = service.create_zip_backup("BROKEN")

        assert result is None
