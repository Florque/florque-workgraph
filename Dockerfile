# The service image. It also carries the wheels of every package in /app/dist, which
# deploy/deploy.sh publishes at https://<server>/dist/ for `uv tool install florque-cli`.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock .python-version ./
COPY packages ./packages
RUN uv sync --frozen --no-dev --no-editable \
 && uv build --all-packages --wheel --out-dir /app/dist

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home /app florque \
 && mkdir -p /data && chown florque /data
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/dist /app/dist
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER florque
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["florque-service", "serve", "--host", "0.0.0.0", "--port", "8000"]
