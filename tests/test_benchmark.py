#!/usr/bin/env python3
"""
Benchmark script to compare performance with/without optimizations
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config
from src.report_generator import generate_csv_report


def benchmark():
    """Run performance benchmarks"""
    print("=" * 70)
    print("  Automate Jira - Performance Benchmark")
    print("=" * 70)
    print()
    
    # Load config
    config = Config.from_env()
    year = 2025
    
    # Test 1: With cache disabled
    print("Test 1: Without cache (simulates first run)")
    print("-" * 70)
    config.jira.enable_cache = False
    start = time.time()
    generate_csv_report(config, year=year, output_file="benchmark_nocache.csv")
    nocache_time = time.time() - start
    print(f"✓ Completed in {nocache_time:.1f}s")
    print()
    
    # Test 2: With cache enabled (first run)
    print("Test 2: With cache enabled (first run)")
    print("-" * 70)
    clear_cache(config.jira.cache_dir)
    config.jira.enable_cache = True
    start = time.time()
    generate_csv_report(config, year=year, output_file="benchmark_cache1.csv")
    cache1_time = time.time() - start
    print(f"✓ Completed in {cache1_time:.1f}s")
    print()
    
    # Test 3: With cache enabled (second run - should be fast)
    print("Test 3: With cache enabled (cached run)")
    print("-" * 70)
    start = time.time()
    generate_csv_report(config, year=year, output_file="benchmark_cache2.csv")
    cache2_time = time.time() - start
    print(f"✓ Completed in {cache2_time:.1f}s")
    print()
    
    # Summary
    print("=" * 70)
    print("  Benchmark Results")
    print("=" * 70)
    print(f"Without cache:        {nocache_time:.1f}s")
    print(f"With cache (1st run): {cache1_time:.1f}s")
    print(f"With cache (2nd run): {cache2_time:.1f}s")
    print()
    print(f"Cache speedup: {nocache_time/cache2_time:.1f}x faster")
    print(f"Improvement:   {((nocache_time - cache2_time) / nocache_time * 100):.0f}% faster")
    print("=" * 70)
    
    # Cleanup
    Path("benchmark_nocache.csv").unlink(missing_ok=True)
    Path("benchmark_cache1.csv").unlink(missing_ok=True)
    Path("benchmark_cache2.csv").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        benchmark()
    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nBenchmark failed: {e}")
        sys.exit(1)
