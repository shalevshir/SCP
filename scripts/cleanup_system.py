#!/usr/bin/env python3
"""
Cleanup Script: Clear Database and Redis Queues

This script cleans up the test environment by:
- Truncating all database tables (candles, features, trades, etc.)
- Deleting all Redis streams
- Clearing consumer groups

Usage:
    poetry run python scripts/cleanup_system.py
    poetry run python scripts/cleanup_system.py --confirm  # Skip confirmation prompt
"""

import argparse
import asyncio
import sys
from typing import Any

import asyncpg
import redis.asyncio as redis
from redis.asyncio import Redis

# Configuration
POSTGRES_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "scp",
    "user": "scp",
    "password": "scp_dev_password",
}

REDIS_URL = "redis://localhost:6379"

# Tables to truncate (in order, respecting foreign keys)
TABLES_TO_TRUNCATE = [
    "trades",
    "state_machine_snapshots",
    "daily_state",
    "htf_bias_history",
    "features",
    "candles",
]

# Redis streams to delete
REDIS_STREAMS = [
    "candles.1m.gc",
    "candles.1m.dxy",
    "features.1m",
    "features.15m",
    "features.1h",
    "htf.bias",
    "signals.pending",
    "trades.opened",
    "trades.closed",
]


async def cleanup_postgres() -> None:
    """Clear all data from PostgreSQL tables."""
    print("\n🗑️  Cleaning PostgreSQL database...")
    
    conn = await asyncpg.connect(**POSTGRES_CONFIG)
    
    try:
        for table in TABLES_TO_TRUNCATE:
            print(f"  • Truncating {table}...")
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE;")
        
        print("✅ PostgreSQL cleanup complete")
    
    except Exception as e:
        print(f"❌ PostgreSQL cleanup failed: {e}")
        raise
    
    finally:
        await conn.close()


async def cleanup_redis() -> None:
    """Delete all Redis streams and consumer groups."""
    print("\n🗑️  Cleaning Redis streams...")
    
    redis_client: Redis = await redis.from_url(REDIS_URL, decode_responses=True)
    
    try:
        for stream in REDIS_STREAMS:
            # Check if stream exists
            exists = await redis_client.exists(stream)
            if exists:
                # Delete the stream (this also deletes consumer groups)
                await redis_client.delete(stream)
                print(f"  • Deleted stream: {stream}")
            else:
                print(f"  • Stream not found (skipping): {stream}")
        
        print("✅ Redis cleanup complete")
    
    except Exception as e:
        print(f"❌ Redis cleanup failed: {e}")
        raise
    
    finally:
        await redis_client.close()


async def get_data_counts() -> dict[str, Any]:
    """Get current data counts before cleanup."""
    counts = {
        "postgres": {},
        "redis": {},
    }
    
    # Use nested try/finally blocks to ensure proper cleanup
    conn = await asyncpg.connect(**POSTGRES_CONFIG)
    try:
        # Get PostgreSQL counts
        for table in TABLES_TO_TRUNCATE:
            try:
                result = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                counts["postgres"][table] = result
            except Exception:
                counts["postgres"][table] = "N/A"
        
        # Create Redis connection only after postgres queries succeed
        redis_client: Redis = await redis.from_url(REDIS_URL, decode_responses=True)
        try:
            # Get Redis stream lengths
            for stream in REDIS_STREAMS:
                try:
                    length = await redis_client.xlen(stream)
                    counts["redis"][stream] = length
                except Exception:
                    counts["redis"][stream] = 0
        finally:
            await redis_client.close()
    
    finally:
        await conn.close()
    
    return counts


def print_data_summary(counts: dict[str, Any]) -> None:
    """Print summary of current data."""
    print("\n📊 Current Data Summary:")
    
    print("\n  PostgreSQL:")
    for table, count in counts["postgres"].items():
        print(f"    • {table}: {count} rows")
    
    print("\n  Redis Streams:")
    for stream, length in counts["redis"].items():
        if length > 0:
            print(f"    • {stream}: {length} messages")


async def main() -> None:
    """Main cleanup function."""
    parser = argparse.ArgumentParser(
        description="Clean up database and Redis queues"
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt (use in scripts)",
    )
    parser.add_argument(
        "--postgres-only",
        action="store_true",
        help="Only clean PostgreSQL database",
    )
    parser.add_argument(
        "--redis-only",
        action="store_true",
        help="Only clean Redis streams",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🧹 SYSTEM CLEANUP SCRIPT")
    print("=" * 70)
    
    # Get current data counts
    try:
        counts = await get_data_counts()
        print_data_summary(counts)
    except Exception as e:
        print(f"\n⚠️  Could not retrieve data counts: {e}")
        counts = None
    
    # Check if there's any data to clean
    if counts:
        has_postgres_data = any(
            count != 0 and count != "N/A" 
            for count in counts["postgres"].values()
        )
        has_redis_data = any(
            length > 0 
            for length in counts["redis"].values()
        )
        
        if not has_postgres_data and not has_redis_data:
            print("\n✨ System is already clean. Nothing to do!")
            return
    
    # Confirmation prompt
    if not args.confirm:
        print("\n⚠️  WARNING: This will DELETE ALL DATA from:")
        if not args.redis_only:
            print("  • PostgreSQL database (all tables)")
        if not args.postgres_only:
            print("  • Redis streams (all queues)")
        
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Cleanup cancelled")
            sys.exit(0)
    
    # Perform cleanup
    try:
        if not args.redis_only:
            await cleanup_postgres()
        
        if not args.postgres_only:
            await cleanup_redis()
        
        print("\n" + "=" * 70)
        print("✅ CLEANUP COMPLETE!")
        print("=" * 70)
        print("\nYou can now:")
        print("  1. Run replay script to load fresh data")
        print("  2. Start live data ingestion")
        print("  3. Begin testing with clean state")
        
    except Exception as e:
        print(f"\n❌ Cleanup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
