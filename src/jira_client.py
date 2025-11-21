"""
Jira API client for fetching worklog data
"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
import requests
from requests.auth import HTTPBasicAuth
import json
import hashlib
from pathlib import Path

from .config import JiraConfig
from .models import Issue, Worklog, Component, Author, WorkType

logger = logging.getLogger(__name__)

# Malaysia timezone (UTC+8)
MALAYSIA_TZ = timezone(timedelta(hours=8))


class JiraClientError(Exception):
    """Base exception for Jira client errors"""
    pass


class JiraAuthenticationError(JiraClientError):
    """Authentication failed"""
    pass


class JiraAPIError(JiraClientError):
    """API request failed"""
    pass


class JiraClient:
    """Client for interacting with Jira API"""
    
    def __init__(self, config: JiraConfig, enable_cache: bool = True, cache_dir: str = ".cache"):
        self.config = config
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(config.username, config.api_token)
        self.base_url = f"{config.url}/rest/api/3"
        self.enable_cache = enable_cache
        self.cache_dir = Path(cache_dir)
        self.cache_hit_count = 0
        self.cache_miss_count = 0
        if enable_cache:
            self.cache_dir.mkdir(exist_ok=True)
    
    def get_cache_timestamp(self) -> Optional[datetime]:
        """Get the oldest cache file timestamp in Malaysia time"""
        if not self.enable_cache or not self.cache_dir.exists():
            return None
        
        cache_files = list(self.cache_dir.glob("*.json"))
        if not cache_files:
            return None
        
        # Get the oldest cache file timestamp and convert to Malaysia time
        oldest_time = min(f.stat().st_mtime for f in cache_files)
        return datetime.fromtimestamp(oldest_time, tz=MALAYSIA_TZ)
    
    def is_using_cache(self) -> bool:
        """Check if any cache was used in this session"""
        return self.cache_hit_count > 0
    
    def _get_cache_key(self, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate cache key from endpoint and params"""
        cache_data = f"{endpoint}:{json.dumps(params, sort_keys=True) if params else ''}"
        return hashlib.md5(cache_data.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Get data from cache if available"""
        if not self.enable_cache:
            return None
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    logger.debug(f"Cache hit: {cache_key}")
                    self.cache_hit_count += 1
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
        return None
    
    def _save_to_cache(self, cache_key: str, data: Dict):
        """Save data to cache"""
        if not self.enable_cache:
            return
        
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f)
            logger.debug(f"Cached: {cache_key}")
        except Exception as e:
            logger.warning(f"Cache write error: {e}")
    
    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        method: str = "GET",
        use_cache: bool = True
    ) -> Dict:
        """Make HTTP request to Jira API with caching support"""
        # Check cache first
        if use_cache and method == "GET":
            cache_key = self._get_cache_key(endpoint, params)
            cached_data = self._get_from_cache(cache_key)
            if cached_data is not None:
                return cached_data
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            logger.debug(f"Making {method} request to {url}")
            response = self.session.request(method, url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Save to cache
            if use_cache and method == "GET":
                self._save_to_cache(cache_key, data)
                self.cache_miss_count += 1
            return data
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise JiraAuthenticationError("Authentication failed. Check your credentials.")
            elif e.response.status_code == 403:
                raise JiraAuthenticationError("Access forbidden. Check your permissions.")
            else:
                raise JiraAPIError(f"API request failed: {e}")
        
        except requests.exceptions.RequestException as e:
            raise JiraAPIError(f"Network error: {e}")
    
    def get_user_details(self, account_id: str) -> Dict:
        """Get user details including active status
        
        The worklog API doesn't always include the 'active' field in author data,
        so we fetch it from the user API endpoint which always includes it.
        Results are cached to avoid repeated API calls for the same user.
        """
        try:
            endpoint = f"user?accountId={account_id}"
            return self._make_request(endpoint, use_cache=True)
        except Exception as e:
            logger.warning(f"Failed to fetch user details for {account_id}: {e}")
            return {}
    
    def get_issues_with_worklog(
        self,
        project_key: str,
        start_date: str,
        end_date: str,
        filter_user: Optional[str] = None
    ) -> List[Dict]:
        """Fetch issues with worklog data"""
        
        # Build JQL query
        jql_parts = [
            f'project = {project_key}',
            f'worklogDate >= "{start_date}"',
            f'worklogDate <= "{end_date}"'
        ]
        
        if filter_user:
            jql_parts.append(f'worklogAuthor = "{filter_user}"')
        
        jql = ' AND '.join(jql_parts)
        
        params = {
            'jql': jql,
            'fields': 'key,summary,components,labels,issuetype,worklog,customfield_*',
            'expand': 'worklog',
            'maxResults': 1000  # Increased from 100 to 1000 for better performance
        }
        
        issues = []
        start_at = 0
        
        logger.info(f"Fetching issues for {project_key} from {start_date} to {end_date}")
        
        while True:
            params['startAt'] = start_at
            response = self._make_request("search/jql", params)
            
            batch = response.get('issues', [])
            issues.extend(batch)
            
            total = response.get('total', 0)
            logger.debug(f"Fetched {len(issues)}/{total} issues")
            
            if start_at + len(batch) >= total:
                break
            
            start_at += len(batch)
        
        logger.info(f"Fetched {len(issues)} issues for {project_key}")
        return issues
    
    def parse_issue(self, issue_data: Dict, fetch_all_worklogs: bool = True) -> Issue:
        """Parse raw issue data into Issue model"""
        fields = issue_data.get('fields', {})
        issue_key = issue_data.get('key')
        
        # Parse components
        components = [
            Component(name=c['name'], id=c.get('id'))
            for c in fields.get('components', [])
        ]
        
        if not components:
            components = [Component(name='Unassigned')]
        
        # Parse worklogs - intelligently fetch all if needed
        worklogs = []
        worklog_data = fields.get('worklog', {})
        worklog_list = worklog_data.get('worklogs', [])
        total_worklogs = worklog_data.get('total', len(worklog_list))
        
        # Only fetch all worklogs if there are MORE than what's in the response
        # This optimization prevents unnecessary API calls
        if fetch_all_worklogs and total_worklogs > len(worklog_list):
            logger.debug(f"{issue_key}: Fetching all {total_worklogs} worklogs (response had {len(worklog_list)})")
            worklog_list = self.get_all_worklogs_for_issue(issue_key)
        # No warning needed - we have all the worklogs we need
        
        for wl in worklog_list:
            author_data = wl.get('author', {})
            
            # Get active status - fetch from user API if not in worklog response
            active = author_data.get('active')
            if active is None and author_data.get('accountId'):
                # Fetch user details to get active status
                user_details = self.get_user_details(author_data.get('accountId'))
                active = user_details.get('active', True)
            elif active is None:
                # No account ID and no active field, default to True
                active = True
            
            author = Author(
                email=author_data.get('emailAddress', 'unknown'),
                display_name=author_data.get('displayName', 'Unknown'),
                account_id=author_data.get('accountId'),
                active=active
            )
            
            worklog = Worklog(
                id=wl.get('id'),
                author=author,
                time_spent_seconds=wl.get('timeSpentSeconds', 0),
                started=datetime.fromisoformat(wl['started'].replace('Z', '+00:00')),
                issue_key=issue_data.get('key'),
                comment=wl.get('comment', {}).get('content') if isinstance(wl.get('comment'), dict) else None
            )
            worklogs.append(worklog)
        
        # Determine work type
        work_type = self._categorize_work_type(fields)
        
        return Issue(
            key=issue_data.get('key'),
            summary=fields.get('summary', 'No summary'),
            issue_type=fields.get('issuetype', {}).get('name', 'Unknown'),
            components=components,
            labels=fields.get('labels', []),
            work_type=work_type,
            worklogs=worklogs,
            custom_fields={k: v for k, v in fields.items() if k.startswith('customfield_')}
        )
    
    def _categorize_work_type(self, fields: Dict) -> WorkType:
        """Categorize work type based on issue fields"""
        
        # Check custom field for man hours category
        manhours_category_field = fields.get('customfield_10082')
        if manhours_category_field:
            category_value = self._extract_field_value(manhours_category_field).lower()
            
            if 'maintenance' in category_value:
                return WorkType.MAINTENANCE
            elif 'development' in category_value:
                return WorkType.DEVELOPMENT
        
        # Check other custom fields
        for field_key in ['customfield_10048', 'customfield_10081']:
            field_value = fields.get(field_key)
            if field_value:
                category_value = self._extract_field_value(field_value).lower()
                
                if 'maintenance' in category_value:
                    return WorkType.MAINTENANCE
                elif 'development' in category_value:
                    return WorkType.DEVELOPMENT
        
        # Fallback to issue type and labels
        issue_type = fields.get('issuetype', {}).get('name', '').lower()
        labels = [label.lower() for label in fields.get('labels', [])]
        
        maintenance_types = ['bug', 'hotfix', 'support', 'incident', 'defect']
        maintenance_labels = ['maintenance', 'bugfix', 'hotfix', 'support', 'patch']
        
        if (any(mt in issue_type for mt in maintenance_types) or 
            any(ml in labels for ml in maintenance_labels)):
            return WorkType.MAINTENANCE
        
        return WorkType.DEVELOPMENT
    
    def _extract_field_value(self, field_value) -> str:
        """Extract string value from various field formats"""
        if isinstance(field_value, dict):
            return field_value.get('value', '')
        elif isinstance(field_value, str):
            return field_value
        else:
            return str(field_value)
    
    def get_all_worklogs_for_issue(self, issue_key: str) -> List[Dict]:
        """Fetch all worklogs for a specific issue"""
        try:
            worklogs = []
            start_at = 0
            max_results = 1000  # Increased from 100 to 1000
            
            while True:
                response = self._make_request(
                    f"issue/{issue_key}/worklog",
                    params={'startAt': start_at, 'maxResults': max_results}
                )
                
                batch = response.get('worklogs', [])
                worklogs.extend(batch)
                
                total = response.get('total', 0)
                
                if start_at + len(batch) >= total:
                    break
                
                start_at += len(batch)
            
            logger.debug(f"Fetched {len(worklogs)} worklogs for {issue_key}")
            return worklogs
            
        except JiraClientError as e:
            logger.warning(f"Failed to fetch worklogs for {issue_key}: {e}")
            return []
    
    def get_all_projects(self) -> List[str]:
        """Fetch all accessible project keys"""
        try:
            logger.info("Fetching all accessible projects...")
            response = self._make_request("project")
            
            project_keys = [project['key'] for project in response]
            logger.info(f"Found {len(project_keys)} projects: {', '.join(project_keys)}")
            
            return project_keys
        except JiraClientError as e:
            logger.error(f"Failed to fetch projects: {e}")
            return []
    
    def test_connection(self) -> bool:
        """Test connection to Jira"""
        try:
            self._make_request("myself")
            logger.info("Successfully connected to Jira")
            return True
        except JiraClientError as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def get_all_projects(self) -> List[str]:
        """Fetch all accessible project keys"""
        try:
            response = self._make_request("project")
            projects = [p['key'] for p in response if 'key' in p]
            logger.info(f"Found {len(projects)} accessible projects")
            return projects
        except JiraClientError as e:
            logger.error(f"Failed to fetch projects: {e}")
            return []
