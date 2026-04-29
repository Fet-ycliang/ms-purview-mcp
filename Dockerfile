# syntax=docker/dockerfile:1

FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
# Keep local/corporate uv.lock behavior intact, but install from public PyPI in Azure remote builds.
RUN uv export --frozen --no-dev --no-emit-project --no-hashes --format requirements-txt --output-file requirements-docker.txt
RUN python -m venv .venv && \
    .venv/bin/pip install --isolated -i https://pypi.org/simple -r requirements-docker.txt

FROM python:3.12-slim AS final

WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY pyproject.toml ./
COPY src/ ./src/
RUN .venv/bin/pip install --isolated -i https://pypi.org/simple --no-deps .

ENV PATH="/app/.venv/bin:$PATH"
ENV USE_HTTP=true
ENV PORT=8080

EXPOSE 8080

ENTRYPOINT ["python", "-m", "purview_mcp.server"]
