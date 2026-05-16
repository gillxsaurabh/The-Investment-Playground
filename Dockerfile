# Stage 1: Build Angular frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend/cognicap-app
# Bump FRONTEND_VER to bust Railway's layer cache and force ng build
ARG FRONTEND_VER=20
COPY frontend/cognicap-app/package*.json ./
RUN npm ci
COPY frontend/cognicap-app/ ./
RUN npx ng build --configuration=production

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies + su-exec for privilege drop in entrypoint
ARG DEPS_VER=4
COPY backend/requirements.txt ./backend/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends su-exec && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy Gunicorn config into backend dir so it's accessible from WORKDIR
COPY gunicorn.conf.py ./backend/gunicorn.conf.py

# Copy backend source
COPY backend/ ./backend/

# Copy Angular build output from Stage 1
COPY --from=frontend-builder /app/frontend/cognicap-app/dist ./frontend/cognicap-app/dist

# Create state directory and non-root user
RUN mkdir -p backend/data/state
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app

# Entrypoint fixes Railway volume ownership (mounted as root) then drops to appuser
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Health check for container orchestrators
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-5000}/health/live')"

# Set working directory to backend so relative imports work
WORKDIR /app/backend
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:create_app()"]
