FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

RUN python -m pip install --no-cache-dir uv==0.11.28
COPY apps/api/pyproject.toml apps/api/uv.lock ./
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./
COPY apps/api/migrations ./migrations
COPY scripts/init_checkpoints.py ./scripts/init_checkpoints.py
COPY scripts/bootstrap_connected.py ./scripts/bootstrap_connected.py
RUN uv sync --locked --no-dev --no-cache

RUN mkdir -p /app/data/uploads
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python scripts/init_checkpoints.py && exec uvicorn supportpilot.api:app --host 0.0.0.0 --port 8000"]
