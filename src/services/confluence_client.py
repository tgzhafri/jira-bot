"""
Confluence Cloud API client using atlassian-python-api.

Wraps the Confluence class from atlassian-python-api to provide
page content retrieval, attachment downloads, and space listing
for backup operations.

Performance features:
- Retry with exponential backoff on transient failures
- Minimal expansion fields by default
- Generator-based page fetching for memory efficiency
- Pagination with configurable page sizes
"""

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
    """Decorator that retries Confluence API calls on transient failures.

    Handles connection errors and server errors with exponential backoff.
    Does not retry on authentication errors.
    """
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
    """Client for interacting with Confluence Cloud REST API.

    Uses atlassian-python-api under the hood for all API calls.
    Provides methods needed for page-level backup operations.

    Features:
    - Automatic retry with exponential backoff
    - Generator-based page fetching for memory efficiency
    - Configurable page sizes for pagination
    """

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

    def get_all_pages_from_space(
        self, space_key: str, expand: str = "body.storage,version,ancestors"
    ) -> List[Dict[str, Any]]:
        """Get all pages from a space with their storage format body.

        Note: For large spaces, prefer get_all_pages_from_space_generator()
        to avoid loading all pages into memory.

        Args:
            space_key: The space key to fetch pages from.
            expand: Comma-separated list of fields to expand.

        Returns:
            List of page dicts with full content in storage format.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        return list(self.get_all_pages_from_space_generator(space_key, expand))

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
        """Get all attachments metadata for a page.

        Args:
            page_id: The page ID.

        Returns:
            List of attachment metadata dicts.

        Raises:
            ConfluenceClientError: If the API request fails.
        """
        try:
            result = self._confluence.get_attachments_from_content(page_id)
            return result.get("results", [])
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to fetch attachments for page {}: {}".format(page_id, e)
            ) from e

    @_retry_on_transient
    def download_attachments_from_page(
        self, page_id: str
    ) -> Dict[str, bytes]:
        """Download all attachments from a page into memory.

        Uses the library's built-in download method which handles
        authentication correctly for Confluence Cloud.

        Args:
            page_id: The page ID.

        Returns:
            Dict mapping filename to raw bytes content.

        Raises:
            ConfluenceClientError: If the download fails.
        """
        try:
            result = self._confluence.download_attachments_from_page(
                page_id, to_memory=True
            )
            # Result is either a dict {filename: BytesIO} or an error string
            if isinstance(result, str):
                return {}
            # Convert BytesIO objects to bytes
            return {
                filename: bio.getvalue()
                for filename, bio in result.items()
            }
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to download attachments for page {}: {}".format(page_id, e)
            ) from e

    @_retry_on_transient
    def download_attachment(self, download_url: str) -> bytes:
        """Download a single attachment by its download URL path.

        Uses the atlassian-python-api's built-in GET method which properly
        handles authentication for Confluence Cloud.

        Args:
            download_url: The relative download path from attachment metadata.

        Returns:
            Raw bytes of the attachment.

        Raises:
            ConfluenceClientError: If the download fails.
        """
        try:
            response = self._confluence.get(
                download_url, not_json_response=True
            )
            return response
        except Exception as e:
            raise ConfluenceClientError(
                "Failed to download attachment: {}".format(e)
            ) from e
