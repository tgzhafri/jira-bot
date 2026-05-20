"""Tests for ConfluenceClient URL construction and API methods."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.config import AtlassianConfig
from src.services.confluence_client import (
    ConfluenceClient,
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
        c = ConfluenceClient(config)
    return c


class TestClientInitialization:
    """Test that the client initializes with correct base URL."""

    def test_appends_wiki_to_url(self, config):
        with patch("src.services.confluence_client.Confluence") as MockConfluence:
            MockConfluence.return_value = MagicMock()
            client = ConfluenceClient(config)
            call_kwargs = MockConfluence.call_args[1]
            assert call_kwargs["url"] == "https://mysite.atlassian.net/wiki"
            assert client._base_url == "https://mysite.atlassian.net"

    def test_does_not_double_wiki(self):
        config = AtlassianConfig(
            url="https://mysite.atlassian.net/wiki",
            username="admin@example.com",
            api_token="test-token-long-enough",
        )
        with patch("src.services.confluence_client.Confluence") as MockConfluence:
            MockConfluence.return_value = MagicMock()
            client = ConfluenceClient(config)
            call_kwargs = MockConfluence.call_args[1]
            assert call_kwargs["url"] == "https://mysite.atlassian.net/wiki"
            assert client._base_url == "https://mysite.atlassian.net"

    def test_base_url_strips_trailing_slash(self):
        config = AtlassianConfig(
            url="https://mysite.atlassian.net/wiki/",
            username="admin@example.com",
            api_token="test-token-long-enough",
        )
        with patch("src.services.confluence_client.Confluence") as MockConfluence:
            MockConfluence.return_value = MagicMock()
            client = ConfluenceClient(config)
            assert client._base_url == "https://mysite.atlassian.net"


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

    def test_download_attachments_uses_v1_endpoint(self, client):
        """Verify download uses v1 REST API endpoint as primary method."""
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

        # v1 REST API endpoint is used as primary
        download_call = client._confluence._session.get.call_args_list[1]
        download_call_url = download_call[0][0]
        assert download_call_url == (
            "https://mysite.atlassian.net/wiki/rest/api/content/12345/child/attachment/att-1/download"
        )
        assert "/wiki/wiki/" not in download_call_url

    def test_download_attachments_fallback_to_v1_when_no_download_link(self, client):
        """Verify fallback to v1 REST API when downloadLink is absent."""
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {
            "results": [
                {
                    "id": "att-1",
                    "title": "file.pdf",
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

        # Falls back to v1 endpoint
        download_call = client._confluence._session.get.call_args_list[1]
        download_call_url = download_call[0][0]
        assert download_call_url == (
            "https://mysite.atlassian.net/wiki/rest/api/content/12345/child/attachment/att-1/download"
        )

    def test_download_attachments_archived_page(self, client):
        """Verify download falls back to downloadLink when v1 returns 404.

        The v1 REST API returns 404 for archived pages because it only looks
        for content with status 'current'. The method falls back to using
        downloadLink from v2 metadata.
        """
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {
            "results": [
                {
                    "id": "att-99",
                    "title": "report.xlsx",
                    "downloadLink": "/download/attachments/220758091/report.xlsx?version=2",
                }
            ],
            "_links": {},
        }

        # v1 endpoint returns 404 (archived page)
        mock_404_response = MagicMock()
        mock_404_response.status_code = 404

        # Fallback downloadLink succeeds
        mock_download_response = MagicMock()
        mock_download_response.status_code = 200
        mock_download_response.content = b"excel-bytes"

        client._confluence._session.get.side_effect = [
            mock_list_response,
            mock_404_response,
            mock_download_response,
        ]

        result = client.download_attachments_from_page("220758091")

        assert result == {"report.xlsx": b"excel-bytes"}

        # First download attempt uses v1 endpoint
        first_download_url = client._confluence._session.get.call_args_list[1][0][0]
        assert "/rest/api/content/220758091/child/attachment/att-99/download" in first_download_url

        # Fallback uses downloadLink
        fallback_url = client._confluence._session.get.call_args_list[2][0][0]
        assert fallback_url == (
            "https://mysite.atlassian.net/wiki/download/attachments/220758091/report.xlsx?version=2"
        )

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

    def test_get_attachments_pagination_next_link_with_wiki_prefix(self, client):
        """Verify no double /wiki when _links.next already includes /wiki prefix.

        The Confluence Cloud v2 API returns next links with the /wiki prefix
        (e.g. /wiki/api/v2/pages/{id}/attachments?cursor=...). Concatenating
        this with a base URL that already ends in /wiki would produce
        /wiki/wiki/... resulting in 404 errors.
        """
        page1_response = MagicMock()
        page1_response.status_code = 200
        page1_response.json.return_value = {
            "results": [{"id": "att-1", "title": "a.png"}],
            "_links": {
                "next": "/wiki/api/v2/pages/123/attachments?cursor=eyJpZCI6ImF0dDE4Mjg3ODI3OCJ9"
            },
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

        # The critical assertion: no double /wiki in the paginated URL
        second_url = client._confluence._session.get.call_args_list[1][0][0]
        assert "/wiki/wiki/" not in second_url
        assert second_url == (
            "https://mysite.atlassian.net/wiki/api/v2/pages/123/attachments?cursor=eyJpZCI6ImF0dDE4Mjg3ODI3OCJ9"
        )


class TestBuildV2Url:
    """Test _build_v2_url handles various path formats without double /wiki."""

    def test_relative_path_without_wiki(self, client):
        """Relative path gets prepended with confluence url (includes /wiki)."""
        url = client._build_v2_url("/api/v2/pages/123/attachments")
        assert url == "https://mysite.atlassian.net/wiki/api/v2/pages/123/attachments"

    def test_path_with_wiki_prefix(self, client):
        """Path starting with /wiki/ uses base_url to avoid duplication."""
        url = client._build_v2_url("/wiki/api/v2/pages/123/attachments?cursor=abc")
        assert url == "https://mysite.atlassian.net/wiki/api/v2/pages/123/attachments?cursor=abc"
        assert "/wiki/wiki/" not in url

    def test_path_with_wiki_prefix_and_long_cursor(self, client):
        """Real-world cursor token does not cause double /wiki."""
        cursor = "eyJpZCI6ImF0dDE4Mjg3ODI3OCIsImF0dGFjaG1lbnRTb3J0T3JkZXIiOnsiZGlyZWN0aW9uIjoiQVNDRU5ESU5HIiwiZmllbGQiOiJJRCJ9fQ"
        path = "/wiki/api/v2/pages/163479571/attachments?cursor={}".format(cursor)
        url = client._build_v2_url(path)
        assert "/wiki/wiki/" not in url
        assert url.startswith("https://mysite.atlassian.net/wiki/api/v2/")
