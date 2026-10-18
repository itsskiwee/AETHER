FROM node:22-bookworm-slim AS console
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e './backend[geo,api]'
COPY --from=console /build/frontend/dist ./frontend/dist
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1 PORT=8080
RUN useradd --uid 10001 --create-home aether
USER aether
EXPOSE 8080
CMD ["sh", "-c", "exec python -m uvicorn scripts.hosted_app:app --host 0.0.0.0 --port \"${PORT:-8080}\""]
