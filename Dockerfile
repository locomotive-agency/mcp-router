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

# Install tini for proper signal handling
RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*

# Use tini as entrypoint and our CLI as the command
ENTRYPOINT ["tini", "-s", "--"]
CMD ["python", "-m", "mcp_anywhere", "serve", "http"]