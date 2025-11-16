#!/usr/bin/env python3
"""
Utility script to clear the Jira API cache
"""

import sys
import shutil
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config


def clear_cache(cache_dir: str = None):
    """Clear the cache directory"""
    if cache_dir is None:
        try:
            config = Config.from_env()
            cache_dir = config.jira.cache_dir
        except:
            cache_dir = ".cache"
    
    cache_path = Path(cache_dir)
    
    if cache_path.exists():
        print(f"Clearing cache directory: {cache_path}")
        shutil.rmtree(cache_path)
        print("✓ Cache cleared successfully")
    else:
        print(f"Cache directory does not exist: {cache_path}")


if __name__ == "__main__":
    clear_cache()
