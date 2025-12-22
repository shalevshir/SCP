# Build from services/ directory: docker build -f htf-bias/Dockerfile .
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.7.0

# Copy shared library first (dependency)
COPY shared/ ./shared/

# Copy service dependency files
COPY htf-bias/pyproject.toml htf-bias/poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY htf-bias/src/ ./src/

RUN poetry install --no-interaction --no-ansi

EXPOSE 8003

CMD ["poetry", "run", "python", "-m", "htf_bias_svc.main"]
