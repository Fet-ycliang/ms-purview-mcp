# syntax=docker/dockerfile:1

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS final

WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY src/ ./src/

ENV PATH="/app/.venv/bin:$PATH"
ENV USE_HTTP=true
ENV PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "-m", "purview_mcp.server"]
