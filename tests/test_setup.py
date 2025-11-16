#!/usr/bin/env python3
"""
Verify the Automate Jira setup
"""

import sys
from pathlib import Path

def check_imports():
    """Check if all imports work"""
    print("Checking imports...")
    
    try:
        from src.config import Config, JiraConfig, ReportConfig
        print("  ✅ Config imports OK")
    except ImportError as e:
        print(f"  ❌ Config import failed: {e}")
        return False
    
    try:
        from src.models import Issue, Worklog, Author, Component
        print("  ✅ Models imports OK")
    except ImportError as e:
        print(f"  ❌ Models import failed: {e}")
        return False
    
    try:
        from src.jira_client import JiraClient
        print("  ✅ JiraClient import OK")
    except ImportError as e:
        print(f"  ❌ JiraClient import failed: {e}")
        return False
    
    try:
        from src.processors import WorklogProcessor
        print("  ✅ Processors import OK")
    except ImportError as e:
        print(f"  ❌ Processors import failed: {e}")
        return False
    
    try:
        from src.exporters import CSVExporter
        print("  ✅ Exporters import OK")
    except ImportError as e:
        print(f"  ❌ Exporters import failed: {e}")
        return False
    
    try:
        from src.utils import get_month_range, format_date_for_jql, setup_logging
        print("  ✅ Utils imports OK")
    except ImportError as e:
        print(f"  ❌ Utils import failed: {e}")
        return False
    
    return True

def check_structure():
    """Check if directory structure is correct"""
    print("\nChecking directory structure...")
    
    required_dirs = [
        "src",
        "src/processors",
        "src/exporters",
        "src/utils",
        "scripts",
        "tests"
    ]
    
    for dir_path in required_dirs:
        if Path(dir_path).exists():
            print(f"  ✅ {dir_path}/ exists")
        else:
            print(f"  ❌ {dir_path}/ missing")
            return False
    
    required_files = [
        "src/__init__.py",
        "src/config.py",
        "src/models.py",
        "src/jira_client.py",
        "scripts/generate_report.py",
        "scripts/cli.py",
        "setup.py",
        "requirements.txt",
        "README.md"
    ]
    
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"  ✅ {file_path} exists")
        else:
            print(f"  ❌ {file_path} missing")
            return False
    
    return True

def check_config():
    """Check if .env file exists"""
    print("\nChecking configuration...")
    
    if Path(".env").exists():
        print("  ✅ .env file exists")
        
        # Try to load config
        try:
            from src.config import Config
            config = Config.from_env()
            print("  ✅ Configuration loads successfully")
            print(f"     - Jira URL: {config.jira.url}")
            print(f"     - Projects: {', '.join(config.jira.project_keys)}")
            return True
        except ValueError as e:
            print(f"  ⚠️  Configuration error: {e}")
            print("     Please check your .env file")
            return False
    else:
        print("  ⚠️  .env file not found")
        print("     Create .env file with your Jira credentials")
        print("     See config.env.example for template")
        return False

def main():
    """Run all checks"""
    print("="*60)
    print("  Automate Jira - Setup Verification")
    print("="*60)
    
    checks = [
        ("Imports", check_imports),
        ("Structure", check_structure),
        ("Configuration", check_config)
    ]
    
    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))
    
    print("\n" + "="*60)
    print("  Summary")
    print("="*60)
    
    all_passed = True
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {name}: {status}")
        if not result:
            all_passed = False
    
    print("="*60)
    
    if all_passed:
        print("\n✨ All checks passed! You're ready to generate reports.")
        print("\nNext steps:")
        print("  1. Run: python scripts/generate_report.py")
        print("  2. Or: python scripts/cli.py --help")
        return 0
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
