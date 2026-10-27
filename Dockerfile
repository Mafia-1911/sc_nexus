# One Python image for api, worker and one-off jobs (migrate, seed). uv workspace, Python 3.12.
FROM python:3.12-slim AS app
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app
# OpenMP for LightGBM (C4) and expat for osmium (C3 graph build).
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libexpat1 \
 && rm -rf /var/lib/apt/lists/*
# Dependencies first (cached layer), then the source.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY packages/connectors/pyproject.toml packages/connectors/pyproject.toml
COPY packages/sim/pyproject.toml packages/sim/pyproject.toml
COPY packages/c1_supplier_graph/pyproject.toml packages/c1_supplier_graph/pyproject.toml
COPY packages/c2_trade_news/pyproject.toml packages/c2_trade_news/pyproject.toml
COPY packages/nexus/pyproject.toml packages/nexus/pyproject.toml
COPY packages/c3_routing/pyproject.toml packages/c3_routing/pyproject.toml
COPY packages/c4_port_dwell/pyproject.toml packages/c4_port_dwell/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml
COPY apps/worker/pyproject.toml apps/worker/pyproject.toml
RUN mkdir -p packages/core/src/cportal_core packages/connectors/src/cportal_connectors \
      packages/sim/src/cportal_sim packages/c1_supplier_graph/src/cportal_c1 \
      packages/c2_trade_news/src/cportal_c2 packages/nexus/src/cportal_nexus \
      packages/c3_routing/src/cportal_c3 packages/c4_port_dwell/src/cportal_c4 \
      apps/api/src/cportal_api apps/worker/src/cportal_worker \
 && uv sync --frozen --no-dev --no-install-workspace
COPY . .
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "cportal_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
