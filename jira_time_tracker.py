#!/usr/bin/env python3
"""
Jira Time Tracking Report Generator
"""

import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta
from collections import defaultdict
import os
from typing import Dict, List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class JiraTimeTracker:  
    def __init__(self, jira_url: str, username: str, api_token: str, filter_user: str):
        self.jira_url = jira_url.rstrip('/')
        self.auth = HTTPBasicAuth(username, api_token)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.filter_user = filter_user
        
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        url = f"{self.jira_url}/rest/api/3/{endpoint}"
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_issues_with_worklog(self, project_key: str, start_date: str, end_date: str) -> List[Dict]:
        jql = f"""
        project = {project_key} 
        AND worklogDate >= "{start_date}" 
        AND worklogDate <= "{end_date}"
        AND worklogAuthor = "{self.filter_user}"
        """
        
        params = {
            'jql': jql.strip(),
            'fields': 'key,summary,components,labels,issuetype,worklog,customfield_*',
            'expand': 'worklog',
            'maxResults': 100
        }
        
        issues = []
        start_at = 0
        
        while True:
            params['startAt'] = start_at
            response = self._make_request("search/jql", params)
            issues.extend(response.get('issues', []))
            
            if start_at + len(response.get('issues', [])) >= response.get('total', 0):
                break
            start_at += len(response.get('issues', []))
            
        return issues
    
    def categorize_work_type(self, issue: Dict) -> str:
        fields = issue.get('fields', {})
        
        manhours_category_field = fields.get('customfield_10082')
        if manhours_category_field:
            if isinstance(manhours_category_field, dict):
                category_value = manhours_category_field.get('value', '').lower()
            elif isinstance(manhours_category_field, str):
                category_value = manhours_category_field.lower()
            else:
                category_value = str(manhours_category_field).lower()
            
            if 'maintenance' in category_value:
                return 'Maintenance'
            elif 'development' in category_value:
                return 'Development'
        
        for field_key in ['customfield_10048', 'customfield_10081']:
            field_value = fields.get(field_key)
            if field_value:
                if isinstance(field_value, dict):
                    category_value = field_value.get('value', '').lower()
                elif isinstance(field_value, str):
                    category_value = field_value.lower()
                else:
                    category_value = str(field_value).lower()
                
                if 'maintenance' in category_value:
                    return 'Maintenance'
                elif 'development' in category_value:
                    return 'Development'
        
        issue_type = fields.get('issuetype', {}).get('name', '').lower()
        labels = [label.lower() for label in fields.get('labels', [])]
        
        maintenance_types = ['bug', 'hotfix', 'support', 'incident', 'defect']
        maintenance_labels = ['maintenance', 'bugfix', 'hotfix', 'support', 'patch']
        
        if (any(mt in issue_type for mt in maintenance_types) or 
            any(ml in labels for ml in maintenance_labels)):
            return 'Maintenance'
        
        return 'Development'
    
    def get_week_number(self, date_str: str) -> int:
        date_obj = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
        week_number = ((date_obj.day - 1) // 7) + 1
        return min(week_number, 5)
    
    def process_worklog_data(self, issues: List[Dict], start_date: str, end_date: str) -> Dict:
        data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))
        ticket_details = {}
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        for issue in issues:
            issue_key = issue.get('key')
            issue_summary = issue.get('fields', {}).get('summary', 'No summary')
            components = issue.get('fields', {}).get('components', [])
            worklog_data = issue.get('fields', {}).get('worklog', {})
            
            if not components:
                components = [{'name': 'Unassigned'}]
            
            work_type = self.categorize_work_type(issue)
            
            for worklog in worklog_data.get('worklogs', []):
                # Filter by user
                if worklog.get('author', {}).get('emailAddress') != self.filter_user:
                    continue
                
                # Parse worklog date
                worklog_date = datetime.strptime(worklog['started'].split('T')[0], '%Y-%m-%d')
                
                # Skip if outside date range
                if not (start_dt <= worklog_date <= end_dt):
                    continue
                
                # Get time spent in hours with time factor 
                time_spent_seconds = worklog.get('timeSpentSeconds', 0)
                hours = (time_spent_seconds / 3600) * 1.3
                
                # Get week number
                week = self.get_week_number(worklog['started'])
                
                # Add hours to each component and ticket
                for component in components:
                    component_name = component['name']
                    
                    # Store ticket details
                    ticket_key = f"{component_name}|{work_type}|{issue_key}"
                    if ticket_key not in ticket_details:
                        ticket_details[ticket_key] = {
                            'key': issue_key,
                            'summary': issue_summary,
                            'component': component_name,
                            'work_type': work_type,
                            'total_hours': 0,
                            'weeks': defaultdict(float)
                        }
                    
                    # Add to component totals
                    data[component_name][work_type]['total'][f'W{week}'] += hours
                    
                    # Add to ticket details
                    ticket_details[ticket_key]['total_hours'] += hours
                    ticket_details[ticket_key]['weeks'][f'W{week}'] += hours
        
        # Attach ticket details to the data structure
        data['_ticket_details'] = ticket_details
        return data
    
    def generate_monthly_report(self, project_key: str, year: int, month: int) -> Dict:
        """Generate monthly time tracking report"""
        # Calculate date range for the month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        
        # Get issues with worklog data
        issues = self.get_issues_with_worklog(project_key, start_str, end_str)
        
        # Process the data
        worklog_data = self.process_worklog_data(issues, start_str, end_str)
        
        return worklog_data
    

    
    def generate_yearly_report(self, project_keys: List[str], year: int, save_to_file: bool = True):
        """Generate and print reports for all months in the year for multiple projects"""
        # Capture output for file saving
        output_lines = []
        
        def print_and_capture(text):
            print(text)
            output_lines.append(text)
        
        projects_str = " + ".join(project_keys)
        print_and_capture(f"\n{'#'*105}")
        print_and_capture(f"  JIRA TIME TRACKING REPORT - {year}")
        print_and_capture(f"  Projects: {projects_str}")
        print_and_capture(f"  User: {self.filter_user}")
        print_and_capture(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print_and_capture(f"{'#'*105}")
        
        yearly_total = 0
        yearly_dev = 0
        yearly_maint = 0
        months_with_data = 0
        
        for month in range(1, 13):
            # Combine data from all projects for this month
            combined_worklog_data = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))
            combined_ticket_details = {}
            month_has_data = False
            
            for project_key in project_keys:
                try:
                    worklog_data = self.generate_monthly_report(project_key, year, month)
                    
                    if worklog_data and len(worklog_data) > 1:  # Has data beyond _ticket_details
                        month_has_data = True
                        
                        # Merge ticket details
                        ticket_details = worklog_data.get('_ticket_details', {})
                        for ticket_key, ticket_info in ticket_details.items():
                            # Add project prefix to avoid conflicts
                            prefixed_key = f"{project_key}_{ticket_key}"
                            combined_ticket_details[prefixed_key] = ticket_info.copy()
                        
                        # Merge component data
                        for component_name, component_data in worklog_data.items():
                            if component_name == '_ticket_details':
                                continue
                            for work_type, type_data in component_data.items():
                                if work_type == 'total':
                                    continue
                                weeks = type_data.get('total', {})
                                for week, hours in weeks.items():
                                    combined_worklog_data[component_name][work_type]['total'][week] += hours
                except Exception as e:
                    # Continue processing other projects if one fails
                    print(f"⚠️  Warning: Could not process project {project_key} for {year}-{month:02d}: {e}")
                    continue
            
            if month_has_data:
                months_with_data += 1
                combined_worklog_data['_ticket_details'] = combined_ticket_details
                month_output = self.get_monthly_report_text(projects_str, year, month, combined_worklog_data)
                for line in month_output:
                    print_and_capture(line)
                
                # Calculate monthly totals for yearly summary
                month_total = 0
                month_dev = 0
                month_maint = 0
                
                for component_name, component_data in combined_worklog_data.items():
                    if component_name == '_ticket_details':
                        continue
                    for work_type, type_data in component_data.items():
                        if work_type == 'total':
                            continue
                        weeks = type_data.get('total', {})
                        hours = sum(weeks.values())
                        month_total += hours
                        if work_type == 'Development':
                            month_dev += hours
                        else:
                            month_maint += hours
                
                yearly_total += month_total
                yearly_dev += month_dev
                yearly_maint += month_maint
        
        # Print yearly summary (scaling already applied at granular level)
        print_and_capture(f"\n{'#'*105}")
        print_and_capture(f"  YEARLY SUMMARY - {year}")
        print_and_capture(f"  Projects: {projects_str}")
        print_and_capture(f"{'#'*105}")
        print_and_capture(f"  Months with data: {months_with_data}")
        print_and_capture(f"  Total hours: {yearly_total:.1f}h")
        print_and_capture(f"  Development: {yearly_dev:.1f}h ({yearly_dev/yearly_total*100:.1f}%)" if yearly_total > 0 else "  Development: 0.0h")
        print_and_capture(f"  Maintenance: {yearly_maint:.1f}h ({yearly_maint/yearly_total*100:.1f}%)" if yearly_total > 0 else "  Maintenance: 0.0h")
        print_and_capture(f"  Total days: {yearly_total/8:.1f} days")
        print_and_capture(f"  Average hours/month: {yearly_total/months_with_data:.1f}h" if months_with_data > 0 else "  Average hours/month: 0.0h")
        print_and_capture(f"{'#'*105}")
        
        # Save to file if requested
        if save_to_file:
            filename = f"manhour_report_{year}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write('\n'.join(output_lines))
            print(f"\n📄 Report saved to: {filename}")
    
    def get_monthly_report_text(self, project_key: str, year: int, month: int, worklog_data: Dict) -> List[str]:
        """Get monthly report as list of text lines with ticket details"""
        from collections import defaultdict
        lines = []
        month_name = datetime(year, month, 1).strftime('%B')
        
        lines.append(f"\n{'='*105}")
        lines.append(f"  {month_name} {year} - Time Tracking Report")
        lines.append(f"  Project(s): {project_key} | User: {self.filter_user}")
        lines.append(f"{'='*105}")
        
        if not worklog_data or len(worklog_data) <= 1:  # Only _ticket_details
            lines.append(f"  No worklog data found for {month_name} {year}")
            return lines
        
        # Extract ticket details
        ticket_details = worklog_data.get('_ticket_details', {})
        
        # Calculate totals
        total_hours = 0
        dev_hours = 0
        maint_hours = 0
        
        # Add header with fixed width
        lines.append(f"\n{'Component/Ticket':<50} {'Type':<12} {'Total':<8} {'W1':<6} {'W2':<6} {'W3':<6} {'W4':<6} {'W5':<6}")
        lines.append(f"{'-'*105}")
        
        # Group tickets by component and work type
        component_groups = defaultdict(lambda: defaultdict(list))
        for ticket_key, ticket_info in ticket_details.items():
            component = ticket_info['component']
            work_type = ticket_info['work_type']
            component_groups[component][work_type].append(ticket_info)
        
        # Sort components for consistent output
        for component in sorted(component_groups.keys()):
            work_types = component_groups[component]
            
            for work_type in sorted(work_types.keys()):
                tickets = work_types[work_type]
                
                # Calculate component totals from tickets
                component_total = sum(ticket['total_hours'] for ticket in tickets)
                total_hours += component_total
                
                if work_type == 'Development':
                    dev_hours += component_total
                else:
                    maint_hours += component_total
                
                # Calculate weekly totals from tickets
                w1 = sum(ticket['weeks'].get('W1', 0) for ticket in tickets)
                w2 = sum(ticket['weeks'].get('W2', 0) for ticket in tickets)
                w3 = sum(ticket['weeks'].get('W3', 0) for ticket in tickets)
                w4 = sum(ticket['weeks'].get('W4', 0) for ticket in tickets)
                w5 = sum(ticket['weeks'].get('W5', 0) for ticket in tickets)
                
                # Component header without project prefix
                component_display = component
                if len(component_display) > 50:
                    component_display = component_display[:47] + "..."
                lines.append(f"{component_display:<50} {work_type:<12} {component_total:<8.1f} "
                           f"{w1:<6.1f} {w2:<6.1f} {w3:<6.1f} {w4:<6.1f} {w5:<6.1f}")
                
                # Sort tickets by total hours (descending)
                tickets.sort(key=lambda x: x['total_hours'], reverse=True)
                
                # Display tickets
                for ticket in tickets:
                    ticket_w1 = ticket['weeks'].get('W1', 0)
                    ticket_w2 = ticket['weeks'].get('W2', 0)
                    ticket_w3 = ticket['weeks'].get('W3', 0)
                    ticket_w4 = ticket['weeks'].get('W4', 0)
                    ticket_w5 = ticket['weeks'].get('W5', 0)
                    
                    # Truncate summary if too long
                    summary = ticket['summary']
                    if len(summary) > 35:
                        summary = summary[:32] + "..."
                    
                    ticket_line = f"  └─ {ticket['key']}: {summary}"
                    if len(ticket_line) > 50:
                        ticket_line = ticket_line[:47] + "..."
                    lines.append(f"{ticket_line:<50} {'':<12} {ticket['total_hours']:<8.1f} "
                               f"{ticket_w1:<6.1f} {ticket_w2:<6.1f} {ticket_w3:<6.1f} {ticket_w4:<6.1f} {ticket_w5:<6.1f}")
                
                # Add spacing between components
                lines.append("")
        
        # Add summary
        lines.append(f"{'-'*105}")
        lines.append(f"{'TOTAL':<50} {'':<12} {total_hours:<8.1f}")
        lines.append(f"\nSummary:")
        lines.append(f"  Development: {dev_hours:.1f}h ({dev_hours/total_hours*100:.1f}%)" if total_hours > 0 else "  Development: 0.0h")
        lines.append(f"  Maintenance: {maint_hours:.1f}h ({maint_hours/total_hours*100:.1f}%)" if total_hours > 0 else "  Maintenance: 0.0h")
        lines.append(f"  Total Days: {total_hours/8:.1f} days")
        
        return lines


def main():
    """Main function to run the time tracking report"""
    
    # Load configuration from environment variables
    JIRA_URL = os.getenv('JIRA_URL')
    USERNAME = os.getenv('JIRA_USERNAME')
    API_TOKEN = os.getenv('JIRA_API_TOKEN')
    PROJECT_KEYS_STR = os.getenv('JIRA_PROJECT_KEY')
    
    if not all([JIRA_URL, USERNAME, API_TOKEN, PROJECT_KEYS_STR]):
        print("❌ Missing environment variables. Please check your .env file.")
        print("Required: JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN, JIRA_PROJECT_KEY")
        return
    
    # Parse project keys (support comma-separated values) - robust handling
    PROJECT_KEYS = [key.strip() for key in PROJECT_KEYS_STR.split(',') if key.strip()]
    
    try:
        # Validate project keys
        if not PROJECT_KEYS:
            print("❌ No valid project keys found. Please check JIRA_PROJECT_KEY in your .env file.")
            return
        
        print(f"📋 Processing projects: {', '.join(PROJECT_KEYS)}")
        
        # Initialize tracker with user filter
        tracker = JiraTimeTracker(JIRA_URL, USERNAME, API_TOKEN, USERNAME)
        
        # Generate report for current year
        current_year = datetime.now().year
        tracker.generate_yearly_report(PROJECT_KEYS, current_year)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Please check your Jira credentials and project key.")


if __name__ == "__main__":
    main()