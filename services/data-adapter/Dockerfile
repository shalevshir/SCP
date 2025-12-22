# Build from services/ directory: docker build -f data-adapter/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.7.0

# Copy shared library first (dependency)
COPY shared/ ./shared/

# Copy service dependency files
COPY data-adapter/pyproject.toml data-adapter/poetry.lock* ./

# Install dependencies
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
