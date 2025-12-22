# Build from services/ directory: docker build -f bot-core/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.7.0

# Copy shared library first (dependency)
COPY shared/ ./shared/

# Copy service files maintaining directory structure for relative path resolution
# pyproject.toml references "../shared" so we need bot-core/pyproject.toml -> shared/
COPY bot-core/pyproject.toml bot-core/poetry.lock* ./bot-core/

# Install dependencies from the service directory
WORKDIR /app/bot-core
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY bot-core/src/ ./src/

RUN poetry install --no-interaction --no-ansi

EXPOSE 8004

CMD ["poetry", "run", "python", "-m", "bot_core_svc.main"]
