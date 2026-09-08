FROM nikolaik/python-nodejs:python3.12-nodejs22-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    FRONTEND_DIST_DIR=/app/frontend/dist \
    PORT_BACKEND=8001 \
    PORT_FRONTEND=5173

RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --no-create-home appuser \
    && apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

COPY . .
RUN cd frontend && npm run build

RUN chmod +x /app/docker-entrypoint.sh

RUN chown -R appuser:appgroup /app

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python3 -c "import os, urllib.request; urllib.request.urlopen('http://localhost:%s/api/health' % os.getenv('PORT_BACKEND', '8001'))" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["/app/.venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0"]
