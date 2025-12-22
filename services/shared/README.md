# SCP Shared Library

Common utilities for SCP microservices architecture.

## Installation

```bash
cd services/shared
poetry install
```

## Modules

### Messaging (`scp_shared.messaging`)

Redis Streams pub/sub utilities:

```python
from scp_shared.messaging import RedisStreamPublisher, RedisStreamConsumer, CandleMessage

# Publishing
publisher = RedisStreamPublisher(redis_client)
candle = CandleMessage(timestamp=..., symbol="GC", ...)
await publisher.publish("candles.1m.gc", candle)

# Consuming
consumer = RedisStreamConsumer(
    redis_client,
    stream="candles.1m.gc",
    group="feature-engine",
    consumer_name="instance-1",
    message_type=CandleMessage,
)
messages = await consumer.read(count=10)
```

### Database (`scp_shared.database`)

PostgreSQL/TimescaleDB connection management:

```python
from scp_shared.database import DatabasePool

db_pool = DatabasePool("postgresql://user:pass@localhost/db")
await db_pool.connect()

async with db_pool.acquire() as conn:
    result = await conn.fetchrow("SELECT * FROM candles LIMIT 1")
```

### Health (`scp_shared.health`)

FastAPI health check endpoints:

```python
from fastapi import FastAPI
from scp_shared.health import create_health_router

app = FastAPI()

health_router = create_health_router(
    service_name="data-adapter",
    version="0.1.0",
)
app.include_router(health_router)
```

### Config (`scp_shared.config`)

Base configuration class:

```python
from scp_shared.config import BaseServiceConfig

class MyServiceConfig(BaseServiceConfig):
    my_custom_setting: str

config = MyServiceConfig()  # Loads from environment
```

## Testing

```bash
poetry run pytest
```

## Type Checking

```bash
poetry run mypy src/
```

