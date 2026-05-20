"""Confluence Cloud API client with pagination support."""

import logging
from typing import Any, Dict, Generator, List

from atlassian import Confluence

from ..config import AtlassianConfig

logger = logging.getLogger(__name__)


class ConfluenceClientError(Exception):
    """Base exception for Confluence client errors."""
    pass


class ConfluenceAuthenticationError(ConfluenceClientError):
    """Authentication failed."""
    pass


class ConfluenceClient:
    """Client for Confluence Cloud REST API with pagination."""

    def __init__(self, config: AtlassianConfig):
        self.config = config
        url = config.url.rstrip("/")
        if not url.endswith("/wiki"):
            url = url + "/wiki"

        self._confluence = Confluence(
            url=url,
            username=config.username,
            password=config.api_token,
            api_version="cloud",
        )

        # Base URL without /wiki, for building URLs from API-returned
        # paths that already include /wiki (e.g. pagination next links).
        self._base_url = config.url.rstrip("/")
        if self._base_url.endswith("/wiki"):
            self._base_url = self._base_url[:-5]

    def test_connection(self) -> bool:
        """Test connection to Confluence Cloud."""
        try:
            spaces = self._confluence.get_all_spaces(start=0, limit=1)
            return "results" in spaces
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False

    def get_all_spaces(self) -> List[Dict[str, Any]]:
        """Get all accessible spaces with pagination."""
        try:
            spaces = []
            start = 0
            limit = 100
            while True:
                result = self._confluence.get_all_spaces(
                    start=start, limit=limit, expand="description.plain"
                )
                batch = result.get("results", [])
                if not batch:
                    break
                spaces.extend(batch)
                if result.get("size", 0) < limit:
                    break
                start += limit
            return spaces
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch spaces: {}".format(e)
            ) from e

    def get_all_pages_from_space_generator(
        self, space_key: str, expand: str = "body.storage,version,ancestors"
    ) -> Generator[Dict[str, Any], None, None]:
        """Yield pages from a space using the library's generator.

        Memory-efficient — pages are yielded as fetched rather than
        accumulated into a list.
        """
        try:
            yield from self._confluence.get_all_pages_from_space_as_generator(
                space_key, limit=100, expand=expand
            )
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch pages from space {}: {}".format(space_key, e)
            ) from e

    def get_page_by_id(
        self, page_id: str, expand: str = "body.storage,version,ancestors"
    ) -> Dict[str, Any]:
        """Get a single page by ID."""
        try:
            return self._confluence.get_page_by_id(page_id, expand=expand)
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch page {}: {}".format(page_id, e)
            ) from e

    def _build_v2_url(self, path: str) -> str:
        """Build a full URL for v2 API requests.

        Handles pagination next links that already include /wiki prefix
        to avoid producing /wiki/wiki/ in the URL.
        """
        if path.startswith("/wiki/"):
            return self._base_url + path
        return self._confluence.url + path

    def get_attachments_from_page(self, page_id: str) -> List[Dict[str, Any]]:
        """Get all attachment metadata for a page via the v2 REST API."""
        try:
            attachments = []
            path = "/api/v2/pages/{}/attachments".format(page_id)
            while path:
                response = self._confluence._session.get(
                    self._build_v2_url(path)
                )
                if response.status_code == 401:
                    raise ConfluenceAuthenticationError(
                        "Unauthorized fetching attachments for page {}".format(
                            page_id
                        )
                    )
                response.raise_for_status()
                data = response.json()
                attachments.extend(data.get("results", []))
                path = data.get("_links", {}).get("next")
            return attachments
        except ConfluenceClientError:
            raise
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch attachments for page {}: {}".format(page_id, e)
            ) from e

    def download_attachments_from_page(self, page_id: str) -> Dict[str, bytes]:
        """Download all attachments from a page.

        Uses the v1 REST API endpoint (Basic Auth). Falls back to the
        downloadLink from v2 metadata on 404 (archived pages).
        """
        try:
            attachments = self.get_attachments_from_page(page_id)
            if not attachments:
                return {}

            result = {}
            for att in attachments:
                att_id = att.get("id")
                title = att.get("title", "unknown")
                download_link = att.get("downloadLink")

                if not att_id and not download_link:
                    logger.warning(
                        "Skipping attachment '%s' on page %s: no id or downloadLink",
                        title, page_id,
                    )
                    continue

                response = self._download_single_attachment(
                    page_id, att_id, download_link
                )

                if response.status_code == 401:
                    raise ConfluenceClientError(
                        "Unauthorized downloading attachment '{}' "
                        "for page {}".format(title, page_id)
                    )
                response.raise_for_status()
                result[title] = response.content

            return result
        except ConfluenceClientError:
            raise
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to download attachments for page {}: {}".format(
                    page_id, e
                )
            ) from e

    def _download_single_attachment(self, page_id, att_id, download_link):
        """Download a single attachment, falling back on 404."""
        session = self._confluence._session

        if att_id:
            url = "{}/rest/api/content/{}/child/attachment/{}/download".format(
                self._confluence.url, page_id, att_id
            )
            response = session.get(url, allow_redirects=True)
            if response.status_code == 404 and download_link:
                response = session.get(
                    self._confluence.url + download_link,
                    allow_redirects=True,
                )
        else:
            response = session.get(
                self._confluence.url + download_link,
                allow_redirects=True,
            )

        return response
