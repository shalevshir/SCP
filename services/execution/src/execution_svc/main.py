"""Execution Service main entry point."""

from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from execution_svc.config import ExecutionConfig
from scp_shared.health import create_health_router

config = ExecutionConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    redis_client = redis.Redis.from_url(config.redis_url)
    
    # TODO: Initialize VWAPReclaimStateMachine
    # TODO: Initialize broker client (paper/live)
    # TODO: Subscribe to signals stream
    # TODO: Publish trade events
    
    yield
    
    await redis_client.aclose()


app = FastAPI(
    title="SCP Execution Service",
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
    uvicorn.run(app, host="0.0.0.0", port=8005)

