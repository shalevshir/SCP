# Build from services/ directory: docker build -f feature-engine/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.7.0

# Copy shared library first (dependency)
COPY shared/ ./shared/

# Copy service dependency files
COPY feature-engine/pyproject.toml feature-engine/poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY feature-engine/src/ ./src/

RUN poetry install --no-interaction --no-ansi

EXPOSE 8002

CMD ["poetry", "run", "python", "-m", "feature_engine_svc.main"]
