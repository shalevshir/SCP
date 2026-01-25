"""Consumer group management utilities."""

import redis.asyncio as redis


async def create_consumer_group(
    redis_client: redis.Redis,
    stream: str,
    group: str,
    start_id: str = "0",
) -> bool:
    """Create a consumer group for a stream.

    Args:
        redis_client: Async Redis client
        stream: Stream name
        group: Consumer group name
        start_id: Starting message ID ("0" = from beginning, "$" = from now)

    Returns:
        True if created, False if already exists
    """
    try:
        await redis_client.xgroup_create(
            stream,
            group,
            id=start_id,
            mkstream=True,
        )
        return True
    except redis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            return False
        raise


async def delete_consumer_group(
    redis_client: redis.Redis,
    stream: str,
    group: str,
) -> bool:
    """Delete a consumer group.

    Args:
        redis_client: Async Redis client
        stream: Stream name
        group: Consumer group name

    Returns:
        True if deleted, False if didn't exist
    """
    try:
        result = await redis_client.xgroup_destroy(stream, group)
        return bool(result)
    except redis.ResponseError:
        return False


async def get_consumer_group_info(
    redis_client: redis.Redis,
    stream: str,
) -> list[dict[str, object]]:
    """Get information about all consumer groups for a stream.

    Args:
        redis_client: Async Redis client
        stream: Stream name

    Returns:
        List of consumer group info dicts
    """
    try:
        info = await redis_client.xinfo_groups(stream)
        return info  # type: ignore[return-value]
    except redis.ResponseError:
        return []


async def get_stream_length(
    redis_client: redis.Redis,
    stream: str,
) -> int:
    """Get the number of messages in a stream.

    Args:
        redis_client: Async Redis client
        stream: Stream name

    Returns:
        Number of messages in stream
    """
    length = await redis_client.xlen(stream)
    return int(length) if length else 0
