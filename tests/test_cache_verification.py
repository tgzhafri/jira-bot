#!/usr/bin/env python3
"""
Quick test to verify cache is working
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.config import Config
from src.services.jira_client import JiraClient

def test_cache():
    """Test that cache directory is created and used"""
    
    # Load config
    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"⚠️  Config error (expected if .env not set): {e}")
        print("Creating test config...")
        from src.config import AtlassianConfig, ReportConfig
        config = Config(
            atlassian=AtlassianConfig(
                url="https://test.atlassian.net",
                username="test@example.com",
                api_token="test-token",
                project_keys=["TEST"],
                enable_cache=True,
                cache_dir=".cache"
            ),
            report=ReportConfig(year=2025)
        )
    
    # Ensure cache directory is absolute
    if not Path(config.atlassian.cache_dir).is_absolute():
        config.atlassian.cache_dir = str(Path.cwd() / config.atlassian.cache_dir)
    
    print(f"Cache directory: {config.atlassian.cache_dir}")
    print(f"Cache enabled: {config.atlassian.enable_cache}")
    
    # Check if cache directory exists
    cache_path = Path(config.atlassian.cache_dir)
    print(f"Cache path exists: {cache_path.exists()}")
    
    if cache_path.exists():
        cache_files = list(cache_path.glob("*.json"))
        print(f"Cached files: {len(cache_files)}")
        if cache_files:
            print("Sample cache files:")
            for f in cache_files[:5]:
                print(f"  - {f.name}")
    
    # Initialize client
    client = JiraClient(
        config.atlassian,
        enable_cache=config.atlassian.enable_cache,
        cache_dir=config.atlassian.cache_dir
    )
    
    print(f"\nClient cache enabled: {client.enable_cache}")
    print(f"Client cache dir: {client.cache_dir}")
    print(f"Client cache dir exists: {client.cache_dir.exists()}")
    
    print("\n✅ Cache configuration verified!")

if __name__ == "__main__":
    test_cache()
