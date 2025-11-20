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
    """Clear the cache directory contents without removing the directory"""
    if cache_dir is None:
        try:
            config = Config.from_env()
            cache_dir = config.jira.cache_dir
        except:
            cache_dir = ".cache"
    
    cache_path = Path(cache_dir)
    
    if cache_path.exists() and cache_path.is_dir():
        print(f"Clearing cache directory contents: {cache_path}")
        # Remove all files in the cache directory
        for item in cache_path.iterdir():
            if item.is_file():
                item.unlink()
                print(f"  Deleted: {item.name}")
            elif item.is_dir():
                shutil.rmtree(item)
                print(f"  Deleted directory: {item.name}")
        print("✓ Cache cleared successfully")
    else:
        print(f"Cache directory does not exist: {cache_path}")


if __name__ == "__main__":
    clear_cache()
