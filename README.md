# Quick Start Guide

## 🚀 Get Started in 3 Steps

### 1. Setup Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Credentials
Edit `.env` file with your Jira details:
```bash
JIRA_URL=https://your-company.atlassian.net
JIRA_USERNAME=your-email@company.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=AR,ETL  # Support multiple projects (comma-separated)
```

### 3. Generate Reports
```bash
source venv/bin/activate
python jira_time_tracker.py
```

## 📊 What You Get

Clean terminal output showing your time tracking data with ticket details:

```
=========================================================================================================
  September 2025 - Time Tracking Report
  Project(s): AR + ETL | User: tzf@inscale.net
=========================================================================================================

Component/Ticket                                   Type         Total    W1     W2     W3     W4     W5    
---------------------------------------------------------------------------------------------------------
ERP - Human Resource                               Development  6.0      4.0    2.0    0.0    0.0    0.0   
  └─ AR-3652: Capture External Client Manager                   4.0      4.0    0.0    0.0    0.0    0.0   
  └─ AR-3780: add method translation for inter...               2.0      0.0    2.0    0.0    0.0    0.0   

Unassigned                                         Development  26.0     0.0    18.0   0.0    8.0    0.0   
  └─ ETL-58: Pipeline to load DB Pool employe...                10.0     0.0    10.0   0.0    0.0    0.0   
  └─ ETL-62: Staging Deployment (UAT)                           8.0      0.0    0.0    0.0    8.0    0.0   

---------------------------------------------------------------------------------------------------------
TOTAL                                                           32.0     

Summary:
  Development: 32.0h (100.0%)
  Maintenance: 0.0h (0.0%)
  Total Days: 4.0 days
```

## 📈 Report Features

- **Multi-project support**: Combine multiple projects dynamically (AR + ETL + more)
- **Clean component display**: No project prefixes cluttering component names
- **Robust error handling**: Continues processing if individual projects fail
- **Report scaling**: Optional scaling factor for report values
- **Terminal output**: Clean console display + saved to `manhour_report_2025.txt`
- **User filtering**: Shows only YOUR worklog entries
- **Yearly reports**: All months in current year automatically
- **Ticket details**: Shows individual tickets under each component
- **Weekly breakdown**: W1, W2, W3, W4, W5 within each month
- **Work categorization**: Uses 'Man Hours Category' field from Jira
- **Component grouping**: Organized by Jira components with ticket sub-items
- **Fixed-width columns**: Proper alignment with 50-character component column

## 🔍 Work Type Classification

**Primary Method:** Uses the 'Man Hours Category' custom field (customfield_10082)

**Fallback Method (if manhours category not set):**
- **Maintenance:** Bug, Hotfix, Support, Incident, Defect issue types or maintenance-related labels
- **Development:** All other issue types and labels

## 🧪 Testing

The project includes a comprehensive test suite to ensure reliability:

```bash
# Run all tests
python run_tests.py

# Or use pytest directly
pytest test_jira_time_tracker.py -v

# Run specific test
python run_tests.py TestJiraTimeTracker::test_get_issues_with_worklog_new_api
```

**Test Coverage:**
- API endpoint integration (new `/rest/api/3/search/jql` endpoint)
- Work type categorization logic
- Date and user filtering
- Pagination handling
- Error handling and edge cases
- Report generation and formatting

## 🛠️ Troubleshooting

1. **"No worklog data"**: Check if you have time logged in Jira for the current year
2. **"Connection failed"**: Verify your API token and URL in `.env`
3. **"Missing environment variables"**: Ensure all required fields are in `.env`
4. **"410 Gone" errors**: This has been fixed in v2.0.0 with the new API endpoint

## 📋 Recent Updates

**v2.0.0 (2025-10-01)**
- ✅ Fixed JIRA API deprecation issue (410 Gone error)
- ✅ Updated to new `/rest/api/3/search/jql` endpoint
- ✅ Added comprehensive test suite with 20+ test cases
- ✅ Maintained full backward compatibility

Your streamlined Jira time tracking bot is ready! 🎉
