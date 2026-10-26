# One Python image for api, worker and one-off jobs (migrate, seed). uv workspace, Python 3.12.
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app
# Dependencies first (cached layer), then the source.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/connectors/pyproject.toml packages/connectors/pyproject.toml
COPY packages/sim/pyproject.toml packages/sim/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN mkdir -p packages/core/src/cportal_core packages/connectors/src/cportal_connectors \
      packages/sim/src/cportal_sim apps/api/src/cportal_api \
 && uv sync --frozen --no-dev --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "cportal_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
