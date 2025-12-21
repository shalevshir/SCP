# SCP Infrastructure

Infrastructure setup for the SCP microservices architecture.

## Prerequisites

- Docker with Compose plugin installed
- PostgreSQL client (for database shell access)
- Redis CLI (for Redis testing)

## Quick Start

```bash
# Start infrastructure
make infra-up

# Verify services are running
make infra-ps

# Check logs
make infra-logs

# Stop infrastructure
make infra-down
```

## Services

### Redis
- **Port:** 6379
- **Persistence:** AOF enabled
- **Health check:** `redis-cli ping` should return `PONG`

### PostgreSQL/TimescaleDB
- **Port:** 5432
- **Database:** scp
- **User:** scp
- **Password:** Set via `POSTGRES_PASSWORD` env var (default: `scp_dev_password`)

## Validation

After starting infrastructure, verify:

```bash
# 1. Redis is responding
redis-cli ping
# Expected: PONG

# 2. PostgreSQL is accessible
psql -h localhost -U scp -d scp -c "SELECT 1"
# Expected: Returns 1

# 3. TimescaleDB extension is installed
psql -h localhost -U scp -d scp -c "SELECT extname FROM pg_extension WHERE extname = 'timescaledb'"
# Expected: timescaledb

# 4. Check tables were created
psql -h localhost -U scp -d scp -c "\dt"
# Expected: List of tables (candles, features, trades, etc.)
```

## Database Migrations

Migrations are automatically applied on first startup via Docker's `docker-entrypoint-initdb.d` mechanism.

To manually apply migrations:

```bash
psql -h localhost -U scp -d scp -f migrations/001_initial_schema.sql
psql -h localhost -U scp -d scp -f migrations/002_indexes.sql
```

## Development Mode

For development with verbose logging:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## Test Mode

For CI/testing with ephemeral containers:

```bash
docker compose -f docker-compose.yml -f docker-compose.test.yml up -d
```

## Troubleshooting

### PostgreSQL won't start
- Check if port 5432 is already in use: `lsof -i :5432`
- Check logs: `docker compose logs postgres`

### Redis won't start
- Check if port 6379 is already in use: `lsof -i :6379`
- Check logs: `docker compose logs redis`

### Migrations not applied
- Migrations only run on first startup when database is empty
- To force re-run: `make db-reset` (WARNING: destroys all data)

## Data Persistence

Data is stored in Docker volumes:
- `scp_redis_data` - Redis AOF files
- `scp_postgres_data` - PostgreSQL data directory

To remove all data:

```bash
docker compose down -v
```

