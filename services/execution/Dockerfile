# Build from services/ directory: docker build -f execution/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.7.0

# Copy shared library first (dependency)
COPY shared/ ./shared/

# Copy service files maintaining directory structure for relative path resolution
# pyproject.toml references "../shared" so we need execution/pyproject.toml -> shared/
COPY execution/pyproject.toml execution/poetry.lock* ./execution/

# Install dependencies from the service directory
WORKDIR /app/execution
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY execution/src/ ./src/

RUN poetry install --no-interaction --no-ansi

EXPOSE 8005

CMD ["poetry", "run", "python", "-m", "execution_svc.main"]
