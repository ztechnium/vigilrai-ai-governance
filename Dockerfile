FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install third-party deps first so src/ edits do not invalidate the lock sync cache.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
COPY examples/developer_lab/catalog.py ./examples/developer_lab/catalog.py
RUN uv sync --frozen --no-dev

COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh
COPY data/ ./data/
COPY scripts/seed_mcp_catalog.py ./scripts/seed_mcp_catalog.py
COPY scripts/seed_policy_library.py ./scripts/seed_policy_library.py
COPY scripts/attach_seeded_mcp_to_version.py ./scripts/attach_seeded_mcp_to_version.py

RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN sed -i 's/\r$//' /app/scripts/docker-entrypoint.sh && chmod +x /app/scripts/docker-entrypoint.sh
RUN chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"

EXPOSE 8000
CMD ["/app/scripts/docker-entrypoint.sh"]
