"""Bot Core Service main entry point."""

from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from bot_core_svc.config import BotCoreConfig
from scp_shared.health import create_health_router

config = BotCoreConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    redis_client = redis.Redis.from_url(config.redis_url)
    
    # TODO: Initialize signal scoring engine
    # TODO: Initialize BehaviorGuardrails
    # TODO: Subscribe to features + bias streams
    # TODO: Publish A+ signals
    
    yield
    
    await redis_client.aclose()


app = FastAPI(
    title="SCP Bot Core Service",
    version=config.service_version,
    lifespan=lifespan,
)

health_router = create_health_router(
    service_name=config.service_name,
    version=config.service_version,
)
app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)

