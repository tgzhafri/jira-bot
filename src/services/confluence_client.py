"""Confluence Cloud API client with retry and pagination support."""

import logging
import time
from typing import Any, Dict, Generator, List, Optional

from atlassian import Confluence

from ..config import AtlassianConfig
from ..utils.retry import calculate_backoff_delay

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 30.0
BACKOFF_FACTOR = 2.0


class ConfluenceClientError(Exception):
    """Base exception for Confluence client errors."""
    pass


class ConfluenceAuthenticationError(ConfluenceClientError):
    """Authentication failed."""
    pass


class ConfluenceConnectionError(ConfluenceClientError):
    """Network or connection error."""
    pass


class ConfluenceAPIError(ConfluenceClientError):
    """API request failed."""
    pass


def _retry_on_transient(func):
    """Retry on transient failures with exponential backoff. Does not retry auth errors."""
    def wrapper(*args, **kwargs):
        last_exception = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except ConfluenceAuthenticationError:
                raise
            except ConfluenceClientError as e:
                last_exception = e
                if attempt == MAX_RETRIES:
                    break
                delay = calculate_backoff_delay(
                    attempt, BASE_DELAY, MAX_DELAY, BACKOFF_FACTOR
                )
                logger.warning(
                    "Attempt %d/%d failed for %s: %s. Retrying in %.1fs",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    func.__name__,
                    str(e),
                    delay,
                )
                time.sleep(delay)
            except Exception as e:
                # Wrap unexpected exceptions
                last_exception = ConfluenceClientError(str(e))
                if attempt == MAX_RETRIES:
                    break
                delay = calculate_backoff_delay(
                    attempt, BASE_DELAY, MAX_DELAY, BACKOFF_FACTOR
                )
                logger.warning(
                    "Unexpected error on attempt %d/%d for %s: %s. Retrying in %.1fs",
                    attempt + 1,
                    MAX_RETRIES + 1,
                    func.__name__,
                    str(e),
                    delay,
                )
                time.sleep(delay)
        raise last_exception
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


class ConfluenceCloudClient:
    """Client for Confluence Cloud REST API with retry and pagination."""

    def __init__(self, config: AtlassianConfig):
        """Initialize the Confluence Cloud client.

        Args:
            config: AtlassianConfig with url, username, and api_token.
        """
        self.config = config
        # atlassian-python-api expects the base URL with /wiki for cloud
        url = config.url.rstrip("/")
        if not url.endswith("/wiki"):
            url = url + "/wiki"

        self._confluence = Confluence(
            url=url,
            username=config.username,
            password=config.api_token,
            api_version="cloud",
        )

    def test_connection(self) -> bool:
        """Test connection to Confluence Cloud.

        Returns:
            True if connection is successful, False otherwise.
        """
        try:
            spaces = self._confluence.get_all_spaces(start=0, limit=1)
            return "results" in spaces
        except Exception as e:
            logger.error("Connection test failed: %s", e)
            return False

    @_retry_on_transient
    def get_all_spaces(self) -> List[Dict[str, Any]]:
        """Get all accessible spaces with pagination.

        Returns:
            List of space dicts with keys: key, name, type.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        try:
            spaces = []
            start = 0
            limit = 100  # Larger page size for fewer API calls
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
            raise ConfluenceClientError("Failed to fetch spaces: {}".format(e)) from e

    def get_all_pages_from_space_generator(
        self, space_key: str, expand: str = "body.storage,version,ancestors"
    ) -> Generator[Dict[str, Any], None, None]:
        """Yield pages from a space one at a time using the library's generator.

        Memory-efficient for large spaces — pages are yielded as fetched
        rather than accumulated into a list.

        Args:
            space_key: The space key to fetch pages from.
            expand: Comma-separated list of fields to expand.

        Yields:
            Page dicts with full content in storage format.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        try:
            yield from self._confluence.get_all_pages_from_space_as_generator(
                space_key, limit=100, expand=expand
            )
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch pages from space {}: {}".format(space_key, e)
            ) from e

    @_retry_on_transient
    def get_page_by_id(
        self, page_id: str, expand: str = "body.storage,version,ancestors"
    ) -> Dict[str, Any]:
        """Get a single page by ID with storage format body.

        Args:
            page_id: The page ID.
            expand: Comma-separated list of fields to expand.

        Returns:
            Page dict with content in storage format.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        try:
            return self._confluence.get_page_by_id(page_id, expand=expand)
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch page {}: {}".format(page_id, e)
            ) from e

    @_retry_on_transient
    def get_attachments_from_page(self, page_id: str) -> List[Dict[str, Any]]:
        """Get all attachments metadata for a page using the v2 REST API.

        Uses GET /wiki/api/v2/pages/{id}/attachments which returns attachment
        metadata including a downloadLink for each attachment.

        Args:
            page_id: The page ID.

        Returns:
            List of attachment metadata dicts (v2 format with downloadLink).

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        try:
            attachments = []
            url = "/api/v2/pages/{}/attachments".format(page_id)
            while url:
                response = self._confluence._session.get(
                    self._confluence.url + url
                )
                if response.status_code == 401:
                    raise ConfluenceAuthenticationError(
                        "Unauthorized (401) fetching attachments for page {}".format(
                            page_id
                        )
                    )
                response.raise_for_status()
                data = response.json()
                attachments.extend(data.get("results", []))
                # Handle pagination via _links.next
                links = data.get("_links", {})
                url = links.get("next")
            return attachments
        except ConfluenceClientError:
            raise
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch attachments for page {}: {}".format(page_id, e)
            ) from e

    @_retry_on_transient
    def download_attachments_from_page(
        self, page_id: str
    ) -> Dict[str, bytes]:
        """Download all attachments from a page into memory.

        Uses the Confluence REST API v2 to list attachments and then
        downloads each one via its downloadLink. The downloadLink is a
        relative path appended to the wiki base URL.

        See: https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-attachment/#api-pages-id-attachments-get

        Args:
            page_id: The page ID.

        Returns:
            Dict mapping filename to raw bytes content.

        Raises:
            ConfluenceClientError: If the download fails.
        """
        try:
            attachments = self.get_attachments_from_page(page_id)
            if not attachments:
                return {}

            result = {}
            for att in attachments:
                download_link = att.get("downloadLink")
                title = att.get("title", "unknown")
                if not download_link:
                    logger.warning(
                        "No downloadLink for attachment '%s' on page %s",
                        title, page_id,
                    )
                    continue

                # downloadLink is relative to the wiki base URL
                download_url = self._confluence.url + download_link
                response = self._confluence._session.get(download_url)
                if response.status_code == 401:
                    raise ConfluenceClientError(
                        "Unauthorized (401) downloading attachment '{}' "
                        "for page {}".format(title, page_id)
                    )
                response.raise_for_status()
                result[title] = response.content

            return result
        except ConfluenceClientError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise ConfluenceClientError(
                    "Unauthorized (401) downloading attachments for page {}".format(
                        page_id
                    )
                ) from e
            raise ConfluenceClientError(
                "Failed to download attachments for page {}: {}".format(page_id, e)
            ) from e
