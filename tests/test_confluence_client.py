"""Tests for ConfluenceCloudClient URL construction and API methods."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.config import AtlassianConfig
from src.services.confluence_client import (
    ConfluenceCloudClient,
    ConfluenceClientError,
)


@pytest.fixture
def config():
    return AtlassianConfig(
        url="https://mysite.atlassian.net",
        username="admin@example.com",
        api_token="test-token-long-enough",
    )


@pytest.fixture
def client(config):
    with patch("src.services.confluence_client.Confluence") as MockConfluence:
        mock_instance = MagicMock()
        mock_instance.url = "https://mysite.atlassian.net/wiki"
        mock_instance._session = MagicMock()
        MockConfluence.return_value = mock_instance
        c = ConfluenceCloudClient(config)
    return c


class TestClientInitialization:
    """Test that the client initializes with correct base URL."""

    def test_appends_wiki_to_url(self, config):
        with patch("src.services.confluence_client.Confluence") as MockConfluence:
            MockConfluence.return_value = MagicMock()
            ConfluenceCloudClient(config)
            call_kwargs = MockConfluence.call_args[1]
            assert call_kwargs["url"] == "https://mysite.atlassian.net/wiki"

    def test_does_not_double_wiki(self):
        config = AtlassianConfig(
            url="https://mysite.atlassian.net/wiki",
            username="admin@example.com",
            api_token="test-token-long-enough",
        )
        with patch("src.services.confluence_client.Confluence") as MockConfluence:
            MockConfluence.return_value = MagicMock()
            ConfluenceCloudClient(config)
            call_kwargs = MockConfluence.call_args[1]
            assert call_kwargs["url"] == "https://mysite.atlassian.net/wiki"


class TestAttachmentURLConstruction:
    """Test that attachment API calls use the correct URL without double /wiki."""

    def test_get_attachments_url_no_double_wiki(self, client):
        """Verify GET attachments uses /api/v2/ relative to the wiki base URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "_links": {}}
        client._confluence._session.get.return_value = mock_response

        client.get_attachments_from_page("12345")

        called_url = client._confluence._session.get.call_args[0][0]
        assert called_url == "https://mysite.atlassian.net/wiki/api/v2/pages/12345/attachments"
        assert "/wiki/wiki/" not in called_url

    def test_download_attachments_url_no_double_wiki(self, client):
        """Verify download uses downloadLink appended to wiki base URL."""
        # Mock get_attachments_from_page to return one attachment
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {
            "results": [
                {
                    "id": "att-1",
                    "title": "file.pdf",
                    "downloadLink": "/download/attachments/12345/file.pdf?version=1",
                }
            ],
            "_links": {},
        }

        mock_download_response = MagicMock()
        mock_download_response.status_code = 200
        mock_download_response.content = b"fake-pdf-content"

        client._confluence._session.get.side_effect = [
            mock_list_response,
            mock_download_response,
        ]

        result = client.download_attachments_from_page("12345")

        assert result == {"file.pdf": b"fake-pdf-content"}

        # Check the download URL
        download_call_url = client._confluence._session.get.call_args_list[1][0][0]
        assert download_call_url == (
            "https://mysite.atlassian.net/wiki/download/attachments/12345/file.pdf?version=1"
        )
        assert "/wiki/wiki/" not in download_call_url

    def test_get_attachments_paginates(self, client):
        """Verify pagination follows _links.next correctly."""
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "results": [{"id": "att-1", "title": "a.png"}],
            "_links": {"next": "/api/v2/pages/123/attachments?cursor=abc"},
        }

        page2_response = MagicMock()
        page2_response.status_code = 200
        page2_response.json.return_value = {
            "results": [{"id": "att-2", "title": "b.png"}],
            "_links": {},
        }

        client._confluence._session.get.side_effect = [page1_response, page2_response]

        attachments = client.get_attachments_from_page("123")

        assert len(attachments) == 2
        assert attachments[0]["title"] == "a.png"
        assert attachments[1]["title"] == "b.png"

        # Verify second call used the next link relative to base URL
        second_url = client._confluence._session.get.call_args_list[1][0][0]
        assert second_url == (
            "https://mysite.atlassian.net/wiki/api/v2/pages/123/attachments?cursor=abc"
        )
