# control-habits: два образа — api и bot (multi-stage)
# Сборка: docker build --target api -t control-habits-api .
#         docker build --target bot -t control-habits-bot .

FROM python:3.11-slim AS base
WORKDIR /app
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
COPY static ./static

RUN uv sync --no-dev

FROM base AS api
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "control_habits.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS bot
CMD ["uv", "run", "python", "-m", "control_habits.bot.run"]
