"""HTF Bias Service main entry point."""

from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from htf_bias_svc.config import HTFBiasConfig
from scp_shared.health import create_health_router

config = HTFBiasConfig()


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    redis_client = redis.Redis.from_url(config.redis_url)
    
    # TODO: Initialize StreamingHTFBiasCalculator
    # TODO: Subscribe to HTF feature streams
    # TODO: Publish bias updates
    
    yield
    
    await redis_client.aclose()


app = FastAPI(
    title="SCP HTF Bias Service",
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
    uvicorn.run(app, host="0.0.0.0", port=8003)

