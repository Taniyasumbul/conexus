# ---- stage 1: build the React web app (Nexus UI) ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Python API that also serves the built web app ----
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0
COPY pyproject.toml README.md ./
COPY conexus ./conexus
COPY data ./data
COPY results ./results
# editable install keeps the package at /app, so data/, results/ and frontend/dist resolve
RUN pip install --no-cache-dir -e .
COPY --from=web /web/dist ./frontend/dist
EXPOSE 8000
CMD ["conexus-api"]
