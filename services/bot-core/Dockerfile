FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir poetry==1.7.0

COPY pyproject.toml poetry.lock* ./
COPY ../shared ../shared

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

COPY src/ ./src/

RUN poetry install --no-interaction --no-ansi

EXPOSE 8004

CMD ["poetry", "run", "python", "-m", "bot_core_svc.main"]

