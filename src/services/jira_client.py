"""
Jira API client for fetching worklog data.

Optimized for performance with:
- Retry with exponential backoff
- Rate-limit handling (429 responses)
- TTL-based file cache
- Batched user lookups (eliminates N+1)
- Performance tracking and observability
- Field filtering for minimal payloads
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from requests.auth import HTTPBasicAuth

from ..config import AtlassianConfig
from ..models import Author, Component, Issue, Worklog, WorkType
from ..utils.date_utils import MALAYSIA_TZ
from ..utils.performance import PerformanceTracker
from ..utils.retry import RateLimitError, calculate_backoff_delay

logger = logging.getLogger(__name__)

# Default TTL for cache entries (4 hours)
DEFAULT_CACHE_TTL_SECONDS = 4 * 60 * 60


class JiraClientError(Exception):
    """Base exception for Jira client errors."""
    pass


class JiraAuthenticationError(JiraClientError):
    """Authentication failed."""
    pass


class JiraAPIError(JiraClientError):
    """API request failed."""
    pass


class JiraClient:
    """Client for interacting with Jira API.

    Features:
    - Automatic retry with exponential backoff on transient failures
    - Rate-limit (429) handling with Retry-After respect
    - TTL-based file cache for GET requests
    - Batched user-active-status lookups
    - Performance metrics tracking
    - Connection pooling via requests.Session
    """

    # Retry configuration
    MAX_RETRIES = 3
    BASE_DELAY = 1.0
    MAX_DELAY = 60.0
    BACKOFF_FACTOR = 2.0

    # Retryable HTTP status codes
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        config: AtlassianConfig,
        enable_cache: bool = True,
        cache_dir: str = ".cache",
        cache_ttl: int = DEFAULT_CACHE_TTL_SECONDS,
    ):
        self.config = config
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.username, config.api_token)
        # Enable connection pooling
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=0,  # We handle retries ourselves
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.base_url = "{}/rest/api/3".format(config.url)
        self.enable_cache = enable_cache
        self.cache_dir = Path(cache_dir)
        self.cache_ttl = cache_ttl
        self.cache_hit_count = 0
        self.cache_miss_count = 0

        # Performance tracking
        self.perf = PerformanceTracker()

        # Batched user-active-status cache (account_id -> active bool)
        self._user_active_cache = {}  # type: Dict[str, bool]

        if enable_cache:
            self.cache_dir.mkdir(exist_ok=True)

    def get_cache_timestamp(self) -> Optional[datetime]:
        """Get the oldest cache file timestamp in Malaysia time."""
        if not self.enable_cache or not self.cache_dir.exists():
            return None

        cache_files = list(self.cache_dir.glob("*.json"))
        if not cache_files:
            return None

        oldest_time = min(f.stat().st_mtime for f in cache_files)
        return datetime.fromtimestamp(oldest_time, tz=MALAYSIA_TZ)

    def is_using_cache(self) -> bool:
        """Check if any cache was used in this session."""
        return self.cache_hit_count > 0

    # ─── Cache Layer ───────────────────────────────────────────────────

    def _get_cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate cache key from endpoint and params."""
        cache_data = "{}:{}".format(
            endpoint,
            json.dumps(params, sort_keys=True) if params else "",
        )
        return hashlib.md5(cache_data.encode()).hexdigest()

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Get data from cache if available and not expired (TTL-based)."""
        if not self.enable_cache:
            return None

        cache_file = self.cache_dir / "{}.json".format(cache_key)
        if not cache_file.exists():
            return None

        # Check TTL
        file_age = time.time() - cache_file.stat().st_mtime
        if file_age > self.cache_ttl:
            logger.debug("Cache expired (age=%.0fs): %s", file_age, cache_key)
            return None

        try:
            with open(cache_file, "r") as f:
                logger.debug("Cache hit: %s", cache_key)
                self.cache_hit_count += 1
                return json.load(f)
        except Exception as e:
            logger.warning("Cache read error: %s", e)
        return None

    def _save_to_cache(self, cache_key: str, data: Dict) -> None:
        """Save data to cache."""
        if not self.enable_cache:
            return

        cache_file = self.cache_dir / "{}.json".format(cache_key)
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
            logger.debug("Cached: %s", cache_key)
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    # ─── HTTP Layer with Retry ─────────────────────────────────────────

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET",
        use_cache: bool = True,
    ) -> Dict:
        """Make HTTP request to Jira API with caching, retry, and rate-limit handling.

        Args:
            endpoint: API endpoint path (appended to base_url).
            params: Query parameters.
            method: HTTP method.
            use_cache: Whether to use file cache for GET requests.

        Returns:
            Parsed JSON response dict.

        Raises:
            JiraAuthenticationError: On 401/403 responses.
            JiraAPIError: On non-retryable failures.
            RateLimitError: If rate limit persists after all retries.
        """
        # Check cache first
        if use_cache and method == "GET":
            cache_key = self._get_cache_key(endpoint, params)
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                self.perf.record_cached_call(endpoint, method)
                return cached_data

        url = "{}/{}".format(self.base_url, endpoint)
        last_exception = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                with self.perf.track_call(endpoint, method) as metric:
                    logger.debug("Making %s request to %s (attempt %d)", method, url, attempt + 1)
                    response = self.session.request(method, url, params=params)
                    metric.status_code = response.status_code

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else calculate_backoff_delay(
                        attempt, self.BASE_DELAY, self.MAX_DELAY, self.BACKOFF_FACTOR
                    )
                    if attempt == self.MAX_RETRIES:
                        raise RateLimitError(retry_after=delay)
                    logger.warning(
                        "Rate limited (429) on %s, waiting %.1fs (attempt %d/%d)",
                        endpoint,
                        delay,
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                    )
                    time.sleep(delay)
                    continue

                # Handle retryable server errors
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    if attempt == self.MAX_RETRIES:
                        response.raise_for_status()
                    delay = calculate_backoff_delay(
                        attempt, self.BASE_DELAY, self.MAX_DELAY, self.BACKOFF_FACTOR
                    )
                    logger.warning(
                        "Server error %d on %s, retrying in %.1fs (attempt %d/%d)",
                        response.status_code,
                        endpoint,
                        delay,
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                    )
                    time.sleep(delay)
                    continue

                # Handle auth errors (not retryable)
                if response.status_code == 401:
                    raise JiraAuthenticationError(
                        "Authentication failed. Check your credentials."
                    )
                if response.status_code == 403:
                    raise JiraAuthenticationError(
                        "Access forbidden. Check your permissions."
                    )

                response.raise_for_status()
                data = response.json()

                # Save to cache
                if use_cache and method == "GET":
                    self._save_to_cache(cache_key, data)
                    self.cache_miss_count += 1
                return data

            except (JiraAuthenticationError, RateLimitError):
                raise
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt == self.MAX_RETRIES:
                    break
                delay = calculate_backoff_delay(
                    attempt, self.BASE_DELAY, self.MAX_DELAY, self.BACKOFF_FACTOR
                )
                logger.warning(
                    "Network error on %s: %s. Retrying in %.1fs (attempt %d/%d)",
                    endpoint,
                    str(e),
                    delay,
                    attempt + 1,
                    self.MAX_RETRIES + 1,
                )
                time.sleep(delay)

        raise JiraAPIError("API request failed after {} retries: {}".format(
            self.MAX_RETRIES, last_exception
        ))

    # ─── User Active Status (Batched) ─────────────────────────────────

    def prefetch_user_active_status(self, account_ids: Set[str]) -> None:
        """Batch-fetch active status for multiple users.

        Eliminates N+1 queries by fetching all unknown users upfront.
        Results are cached in-memory for the session.

        Args:
            account_ids: Set of Jira account IDs to look up.
        """
        unknown_ids = [
            aid for aid in account_ids
            if aid and aid not in self._user_active_cache
        ]

        if not unknown_ids:
            return

        logger.info("Prefetching active status for %d users", len(unknown_ids))
        for account_id in unknown_ids:
            try:
                endpoint = "user?accountId={}".format(account_id)
                user_data = self._make_request(endpoint, use_cache=True)
                self._user_active_cache[account_id] = user_data.get("active", True)
            except Exception as e:
                logger.warning("Failed to fetch user %s: %s", account_id, e)
                self._user_active_cache[account_id] = True  # Default to active

    def get_user_active_status(self, account_id: str) -> bool:
        """Get cached active status for a user.

        Falls back to API call if not prefetched.

        Args:
            account_id: Jira account ID.

        Returns:
            True if user is active, False otherwise.
        """
        if not account_id:
            return True

        if account_id in self._user_active_cache:
            return self._user_active_cache[account_id]

        # Fallback: single fetch (should be rare after prefetch)
        try:
            endpoint = "user?accountId={}".format(account_id)
            user_data = self._make_request(endpoint, use_cache=True)
            active = user_data.get("active", True)
            self._user_active_cache[account_id] = active
            return active
        except Exception as e:
            logger.warning("Failed to fetch user %s: %s", account_id, e)
            self._user_active_cache[account_id] = True
            return True

    def get_user_details(self, account_id: str) -> Dict:
        """Get user details including active status.

        Results are cached to avoid repeated API calls for the same user.
        """
        try:
            endpoint = "user?accountId={}".format(account_id)
            return self._make_request(endpoint, use_cache=True)
        except Exception as e:
            logger.warning("Failed to fetch user details for %s: %s", account_id, e)
            return {}

    # ─── JQL Search ────────────────────────────────────────────────────

    def _search_issues_jql(
        self,
        jql: str,
        fields: str = "*all",
        expand: Optional[str] = None,
        max_results: int = 1000,
    ) -> List[Dict]:
        """Paginated JQL search using nextPageToken (Jira Cloud recommended).

        Args:
            jql: JQL query string.
            fields: Comma-separated field list or '*all'.
            expand: Optional expand parameter (e.g. 'worklog').
            max_results: Page size per request.

        Returns:
            Aggregated list of raw issue dicts.
        """
        params = {
            "jql": jql,
            "fields": fields,
            "maxResults": max_results,
        }  # type: Dict[str, Any]
        if expand:
            params["expand"] = expand

        issues = []  # type: List[Dict]
        next_page_token = None  # type: Optional[str]

        while True:
            if next_page_token:
                params["nextPageToken"] = next_page_token

            response = self._make_request("search/jql", params)

            batch = response.get("issues", [])
            issues.extend(batch)

            if response.get("isLast", True):
                break

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                logger.warning("isLast=False but no nextPageToken returned")
                break

        return issues

    # ─── Worklog Fetching ──────────────────────────────────────────────

    def get_issues_with_worklog(
        self,
        project_key: str,
        start_date: str,
        end_date: str,
        filter_user: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch issues with worklog data for a date range.

        Uses field filtering to minimize payload size. Only fetches
        fields needed for worklog aggregation.

        Args:
            project_key: Jira project key.
            start_date: Start date string for JQL (YYYY-MM-DD).
            end_date: End date string for JQL (YYYY-MM-DD).
            filter_user: Optional user email to filter worklogs by author.

        Returns:
            List of raw issue dicts with worklog data expanded.
        """
        jql_parts = [
            "project = {}".format(project_key),
            'worklogDate >= "{}"'.format(start_date),
            'worklogDate <= "{}"'.format(end_date),
        ]

        if filter_user:
            jql_parts.append('worklogAuthor = "{}"'.format(filter_user))

        jql = " AND ".join(jql_parts)

        logger.info(
            "Fetching issues for %s from %s to %s",
            project_key, start_date, end_date,
        )

        # Only fetch fields needed for worklog processing
        fields = "key,summary,components,labels,issuetype,worklog,customfield_10082,customfield_10048,customfield_10081"

        issues = self._search_issues_jql(
            jql=jql,
            fields=fields,
            expand="worklog",
            max_results=1000,
        )

        logger.info("Fetched %d issues for %s", len(issues), project_key)
        return issues

    # ─── Issue Parsing ─────────────────────────────────────────────────

    def _parse_components(self, fields: Dict) -> List[Component]:
        """Parse components from issue fields."""
        components = [
            Component(name=c["name"], id=c.get("id"))
            for c in fields.get("components", [])
        ]

        if not components:
            components = [Component(name="Unassigned")]

        return components

    def _get_author_active_status(self, author_data: Dict) -> bool:
        """Get active status for an author using batched cache."""
        active = author_data.get("active")
        if active is not None:
            return active

        account_id = author_data.get("accountId")
        if account_id:
            return self.get_user_active_status(account_id)

        return True

    def _parse_worklogs(self, issue_data: Dict, fetch_all_worklogs: bool) -> List[Worklog]:
        """Parse worklogs from issue data."""
        fields = issue_data.get("fields", {})
        issue_key = issue_data.get("key")

        worklogs = []
        worklog_data = fields.get("worklog", {})
        worklog_list = worklog_data.get("worklogs", [])
        total_worklogs = worklog_data.get("total", len(worklog_list))

        # Only fetch all worklogs if there are MORE than what's in the response
        if fetch_all_worklogs and total_worklogs > len(worklog_list):
            logger.debug(
                "%s: Fetching all %d worklogs (response had %d)",
                issue_key, total_worklogs, len(worklog_list),
            )
            worklog_list = self.get_all_worklogs_for_issue(issue_key)

        for wl in worklog_list:
            author_data = wl.get("author", {})
            active = self._get_author_active_status(author_data)

            author = Author(
                email=author_data.get("emailAddress", "unknown"),
                display_name=author_data.get("displayName", "Unknown"),
                account_id=author_data.get("accountId"),
                active=active,
            )

            worklog = Worklog(
                id=wl.get("id"),
                author=author,
                time_spent_seconds=wl.get("timeSpentSeconds", 0),
                started=datetime.fromisoformat(
                    wl["started"].replace("Z", "+00:00")
                ),
                issue_key=issue_key,
                comment=(
                    wl.get("comment", {}).get("content")
                    if isinstance(wl.get("comment"), dict)
                    else None
                ),
            )
            worklogs.append(worklog)

        return worklogs

    def parse_issue(self, issue_data: Dict, fetch_all_worklogs: bool = True) -> Issue:
        """Parse raw issue data into Issue model."""
        fields = issue_data.get("fields", {})

        components = self._parse_components(fields)
        worklogs = self._parse_worklogs(issue_data, fetch_all_worklogs)
        work_type = self._categorize_work_type(fields)

        return Issue(
            key=issue_data.get("key"),
            summary=fields.get("summary", "No summary"),
            issue_type=fields.get("issuetype", {}).get("name", "Unknown"),
            components=components,
            labels=fields.get("labels", []),
            work_type=work_type,
            worklogs=worklogs,
            custom_fields={
                k: v for k, v in fields.items() if k.startswith("customfield_")
            },
        )

    def _check_field_for_category(self, fields: Dict, field_key: str) -> Optional[WorkType]:
        """Check a specific field for work category keywords."""
        field_value = fields.get(field_key)
        if not field_value:
            return None

        category_value = self._extract_field_value(field_value).lower()

        if "maintenance" in category_value:
            return WorkType.MAINTENANCE
        elif "development" in category_value:
            return WorkType.DEVELOPMENT
        return None

    def _categorize_work_type(self, fields: Dict) -> WorkType:
        """Categorize work type based on issue fields."""
        # Check custom fields for man hours category
        for field_key in ["customfield_10082", "customfield_10048", "customfield_10081"]:
            work_type = self._check_field_for_category(fields, field_key)
            if work_type:
                return work_type

        # Fallback to issue type and labels
        issue_type = fields.get("issuetype", {}).get("name", "").lower()
        labels = [label.lower() for label in fields.get("labels", [])]

        maintenance_types = ["bug", "hotfix", "support", "incident", "defect"]
        maintenance_labels = ["maintenance", "bugfix", "hotfix", "support", "patch"]

        if any(mt in issue_type for mt in maintenance_types) or any(
            ml in labels for ml in maintenance_labels
        ):
            return WorkType.MAINTENANCE

        return WorkType.DEVELOPMENT

    def _extract_field_value(self, field_value) -> str:
        """Extract string value from various field formats."""
        if isinstance(field_value, dict):
            return field_value.get("value", "")
        elif isinstance(field_value, str):
            return field_value
        else:
            return str(field_value)

    # ─── Per-Issue Worklog Fetch ───────────────────────────────────────

    def get_all_worklogs_for_issue(self, issue_key: str) -> List[Dict]:
        """Fetch all worklogs for a specific issue using pagination."""
        try:
            worklogs = []  # type: List[Dict]
            next_page_token = None  # type: Optional[str]

            while True:
                params = {"maxResults": 1000}  # type: Dict[str, Any]
                if next_page_token:
                    params["startAfter"] = next_page_token

                response = self._make_request(
                    "issue/{}/worklog".format(issue_key),
                    params=params,
                )

                batch = response.get("worklogs", [])
                worklogs.extend(batch)

                if response.get("isLast", True):
                    break

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    logger.warning(
                        "isLast=False but no nextPageToken for %s worklogs",
                        issue_key,
                    )
                    break

            logger.debug("Fetched %d worklogs for %s", len(worklogs), issue_key)
            return worklogs

        except JiraClientError as e:
            logger.warning("Failed to fetch worklogs for %s: %s", issue_key, e)
            return []

    # ─── Project Operations ────────────────────────────────────────────

    def get_all_projects(self) -> List[str]:
        """Fetch all accessible project keys."""
        try:
            logger.info("Fetching all accessible projects...")
            response = self._make_request("project")

            project_keys = [project["key"] for project in response]
            logger.info(
                "Found %d projects: %s",
                len(project_keys),
                ", ".join(project_keys),
            )

            return project_keys
        except JiraClientError as e:
            logger.error("Failed to fetch projects: %s", e)
            return []

    def get_project(self, project_key: str) -> Dict:
        """Fetch project details."""
        try:
            return self._make_request("project/{}".format(project_key))
        except JiraClientError as e:
            logger.error("Failed to fetch project %s: %s", project_key, e)
            return {}

    # ─── Backup Operations ─────────────────────────────────────────────

    def get_issue_comments(self, issue_key: str) -> List[Dict]:
        """Fetch all comments for a specific issue using pagination."""
        try:
            comments = []  # type: List[Dict]
            next_page_token = None  # type: Optional[str]

            while True:
                params = {"maxResults": 100}  # type: Dict[str, Any]
                if next_page_token:
                    params["nextPageToken"] = next_page_token

                response = self._make_request(
                    "issue/{}/comment".format(issue_key),
                    params=params,
                )

                batch = response.get("comments", [])
                comments.extend(batch)

                if response.get("isLast", True):
                    break

                next_page_token = response.get("nextPageToken")
                if not next_page_token:
                    logger.warning(
                        "isLast=False but no nextPageToken for %s comments",
                        issue_key,
                    )
                    break

            return comments
        except JiraClientError as e:
            logger.warning("Failed to fetch comments for %s: %s", issue_key, e)
            return []

    def get_issues_by_project(
        self,
        project_key: str,
        fields: str = "*all",
        max_results: int = 100,
    ) -> List[Dict]:
        """Fetch all issues for a project.

        Args:
            project_key: Jira project key.
            fields: Comma-separated field list. Use minimal fields for backup.
            max_results: Page size per request.

        Returns:
            List of raw issue dicts.
        """
        jql = 'project = "{}"'.format(project_key)

        logger.info("Fetching all issues for project %s", project_key)

        issues = self._search_issues_jql(
            jql=jql,
            fields=fields,
            max_results=max_results,
        )

        logger.info("Fetched all %d issues for project %s", len(issues), project_key)
        return issues

    def get_issues_by_project_chunked(
        self,
        project_key: str,
        fields: str = "*all",
        chunk_size: int = 100,
    ) -> List[Dict]:
        """Fetch all issues for a project using larger page sizes for backup.

        Optimized for backup operations where we need all issues.

        Args:
            project_key: Jira project key.
            fields: Comma-separated field list.
            chunk_size: Number of issues per page (larger = fewer API calls).

        Returns:
            List of raw issue dicts.
        """
        return self.get_issues_by_project(
            project_key, fields=fields, max_results=chunk_size
        )

    def download_attachment(self, url: str) -> bytes:
        """Download attachment content from Jira with retry."""
        last_exception = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.debug("Downloading attachment from %s", url)
                response = self.session.get(url, stream=True)

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else calculate_backoff_delay(
                        attempt, self.BASE_DELAY, self.MAX_DELAY, self.BACKOFF_FACTOR
                    )
                    if attempt == self.MAX_RETRIES:
                        raise RateLimitError(retry_after=delay)
                    logger.warning("Rate limited downloading attachment, waiting %.1fs", delay)
                    time.sleep(delay)
                    continue

                response.raise_for_status()
                return response.content

            except (RateLimitError, JiraAuthenticationError):
                raise
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt == self.MAX_RETRIES:
                    break
                delay = calculate_backoff_delay(
                    attempt, self.BASE_DELAY, self.MAX_DELAY, self.BACKOFF_FACTOR
                )
                logger.warning(
                    "Attachment download failed: %s. Retrying in %.1fs",
                    str(e), delay,
                )
                time.sleep(delay)

        raise JiraAPIError(
            "Attachment download failed after {} retries: {}".format(
                self.MAX_RETRIES, last_exception
            )
        )

    def download_attachment_streaming(self, url: str, chunk_size: int = 8192):
        """Download attachment as a generator of chunks (memory-efficient).

        Args:
            url: Attachment download URL.
            chunk_size: Size of each chunk in bytes.

        Yields:
            Bytes chunks of the attachment content.
        """
        logger.debug("Streaming attachment from %s", url)
        response = self.session.get(url, stream=True)
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                yield chunk

    # ─── Connection Test ───────────────────────────────────────────────

    def test_connection(self) -> bool:
        """Test connection to Jira."""
        try:
            self._make_request("myself")
            logger.info("Successfully connected to Jira")
            return True
        except JiraClientError as e:
            logger.error("Connection test failed: %s", e)
            return False

    # ─── Batch Helpers ─────────────────────────────────────────────────

    def prefetch_authors_from_issues(self, issues: List[Dict]) -> None:
        """Extract all unique author account IDs from issues and prefetch their status.

        Call this before parsing issues to eliminate N+1 user lookups.

        Args:
            issues: List of raw issue dicts with worklog data.
        """
        account_ids = set()  # type: Set[str]

        for issue in issues:
            worklog_data = issue.get("fields", {}).get("worklog", {})
            for wl in worklog_data.get("worklogs", []):
                author_data = wl.get("author", {})
                account_id = author_data.get("accountId")
                if account_id and author_data.get("active") is None:
                    account_ids.add(account_id)

        if account_ids:
            self.prefetch_user_active_status(account_ids)
