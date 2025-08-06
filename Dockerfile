# Stage 1: Builder
FROM python:3.11-slim AS builder
WORKDIR /app
COPY . .
COPY pyproject.toml .
COPY uv.lock .
RUN pip install uv && uv sync --locked --no-dev

# Stage 2: Final Image
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY . .
# Ensure data directory exists and has correct permissions
RUN mkdir -p .data && chown -R www-data:www-data .data

EXPOSE 8000
CMD ["uvicorn", "mcp_anywhere.web.app:create_app", "--host", "0.0.0.0", "--port", "8000"]