FROM python:3.11-slim

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.7.0

# Copy dependency files
COPY pyproject.toml poetry.lock* ./
COPY ../shared ../shared

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY src/ ./src/

# Install the application
RUN poetry install --no-interaction --no-ansi

# Expose port for health checks
EXPOSE 8001

# Run the service
CMD ["poetry", "run", "python", "-m", "data_adapter.main"]

