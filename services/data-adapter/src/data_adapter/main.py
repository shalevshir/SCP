"""Data Adapter Service main entry point."""

import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from data_adapter.config import DataAdapterConfig
from scp_shared.health import create_health_router

# Load configuration
config = DataAdapterConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    
    # TODO: Start Databento WebSocket consumer
    # TODO: Initialize candle aggregators
    # TODO: Start publishing to Redis Streams
    
    yield
    
    # Shutdown
    await redis_client.aclose()


# Create FastAPI app
app = FastAPI(
    title="SCP Data Adapter Service",
    version=config.service_version,
    lifespan=lifespan,
)

# Add health check endpoints
health_router = create_health_router(
    service_name=config.service_name,
    version=config.service_version,
)
app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

