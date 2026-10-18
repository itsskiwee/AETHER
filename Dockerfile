FROM --platform=linux/amd64 node:22-bookworm-slim AS console
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM --platform=linux/amd64 python:3.12-slim-bookworm
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e './backend[geo,api]'
COPY --from=console /build/frontend/dist ./frontend/dist
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1 PORT=8080 AETHER_HTTP_HOST=0.0.0.0
RUN useradd --uid 10001 --create-home aether
RUN mkdir -p /app/data/live_context && chown aether:aether /app/data/live_context
USER aether
EXPOSE 8080
CMD ["sh", "scripts/serve_hosted.sh"]
