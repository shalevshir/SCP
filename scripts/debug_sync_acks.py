#!/usr/bin/env python3
"""Debug script to inspect sync.ack stream contents."""

import asyncio
import redis.asyncio as redis
from datetime import datetime


async def main():
    """Check sync.ack stream for messages."""
    redis_client = redis.Redis.from_url("redis://localhost:6379")

    try:
        # Check if stream exists
        exists = await redis_client.exists("sync.ack")
        print(f"sync.ack stream exists: {exists}")

        if exists:
            # Get stream length
            length = await redis_client.xlen("sync.ack")
            print(f"sync.ack stream length: {length}")

            # Read all messages from beginning
            messages = await redis_client.xread({"sync.ack": "0"}, count=100)

            if messages:
                print(f"\nFound {len(messages[0][1])} messages:")
                for msg_id, fields in messages[0][1]:
                    print(f"  {msg_id.decode()}: {fields}")
            else:
                print("No messages in stream")

        # Check consumer groups
        try:
            groups = await redis_client.xinfo_groups("sync.ack")
            print(f"\nConsumer groups on sync.ack: {len(groups)}")
            for group in groups:
                print(f"  Group: {group}")
        except redis.ResponseError as e:
            print(f"\nNo consumer groups: {e}")

    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
