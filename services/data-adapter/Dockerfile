# Build from services/ directory: docker build -f data-adapter/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.7.0

# Copy shared library first (dependency)
COPY shared/ ./shared/

# Copy service files maintaining directory structure for relative path resolution
# pyproject.toml references "../shared" so we need data-adapter/pyproject.toml -> shared/
COPY data-adapter/pyproject.toml data-adapter/poetry.lock* ./data-adapter/

# Install dependencies from the service directory
WORKDIR /app/data-adapter
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY data-adapter/src/ ./src/

# Install the application
RUN poetry install --no-interaction --no-ansi

# Expose port for health checks
EXPOSE 8001

# Run the service
CMD ["poetry", "run", "python", "-m", "data_adapter.main"]
