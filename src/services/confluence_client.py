"""
Confluence Data Center API client for backup and restore operations
"""

import logging
from typing import Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from ..config import AtlassianConfig

logger = logging.getLogger(__name__)


class ConfluenceClientError(Exception):
    """Base exception for Confluence client errors"""
    pass


class ConfluenceAuthenticationError(ConfluenceClientError):
    """Authentication failed (HTTP 401)"""
    pass


class ConfluencePermissionError(ConfluenceClientError):
    """Permission denied (HTTP 403)"""
    pass


class ConfluenceAPIError(ConfluenceClientError):
    """API request failed (other HTTP errors)"""
    pass


class ConfluenceConnectionError(ConfluenceClientError):
    """Network or timeout error"""
    pass


class ConfluenceClient:
    """Client for interacting with Confluence Data Center Backup and Restore API"""

    BASE_PATH = "/rest/api/backup-restore/"
    TIMEOUT = 30  # seconds

    def __init__(self, config: AtlassianConfig):
        self.config = config
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.username, config.api_token)
        self.base_url = config.url

    def _build_url(self, endpoint: str) -> str:
        """Combine base_url + BASE_PATH + endpoint, avoiding double slashes."""
        base = self.base_url.rstrip("/")
        path = self.BASE_PATH
        # Strip leading slash from endpoint to avoid double slashes
        endpoint = endpoint.lstrip("/")
        return f"{base}{path}{endpoint}"

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        stream: bool = False,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """Core HTTP method with error mapping.

        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint path (appended to BASE_PATH)
            json_data: Optional JSON body for the request
            params: Optional query parameters
            stream: Whether to stream the response
            timeout: Optional timeout override (defaults to TIMEOUT)

        Returns:
            requests.Response object

        Raises:
            ConfluenceAuthenticationError: On HTTP 401
            ConfluencePermissionError: On HTTP 403
            ConfluenceAPIError: On other HTTP errors
            ConfluenceConnectionError: On network/timeout errors
        """
        url = self._build_url(endpoint)
        request_timeout = timeout if timeout is not None else self.TIMEOUT

        try:
            logger.debug(f"Making {method} request to {url}")
            response = self.session.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
                stream=stream,
                timeout=request_timeout,
            )
            response.raise_for_status()
            return response

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if status_code == 401:
                raise ConfluenceAuthenticationError(
                    "Authentication failed. Check your credentials."
                )
            elif status_code == 403:
                raise ConfluencePermissionError(
                    "Permission denied. The authenticated user lacks permission "
                    "for the requested operation."
                )
            else:
                body = e.response.text[:1000]
                raise ConfluenceAPIError(
                    f"API request failed with status {status_code}: {body}"
                )

        except requests.exceptions.ConnectionError as e:
            raise ConfluenceConnectionError(
                f"Network error: {e}"
            )

        except requests.exceptions.Timeout as e:
            raise ConfluenceConnectionError(
                f"Request timed out: {e}"
            )

        except requests.exceptions.RequestException as e:
            raise ConfluenceConnectionError(
                f"Request failed: {e}"
            )

        except (ConnectionError, OSError) as e:
            raise ConfluenceConnectionError(
                f"Network error: {e}"
            )

    def test_connection(self) -> bool:
        """Test connection to Confluence Data Center.

        Sends a GET request to a Confluence REST endpoint and returns True
        if the response status is HTTP 200, or False if any error occurs.
        """
        try:
            self._make_request("GET", "")
            logger.info("Successfully connected to Confluence")
            return True
        except ConfluenceClientError as e:
            logger.error(f"Connection test failed: {e}")
            return False
