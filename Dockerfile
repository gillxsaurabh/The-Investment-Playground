# Stage 1: Build Angular frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend/cognicap-app
COPY frontend/cognicap-app/package*.json ./
RUN npm ci
COPY frontend/cognicap-app/ ./
RUN npx ng build --configuration=production

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies (bump DEPS_VER to bust Railway's layer cache)
ARG DEPS_VER=2
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy Gunicorn config
COPY gunicorn.conf.py ./gunicorn.conf.py

# Copy backend source
COPY backend/ ./backend/

# Copy Angular build output from Stage 1
COPY --from=frontend-builder /app/frontend/cognicap-app/dist ./frontend/cognicap-app/dist

# Create state directory (gitignored — must exist at runtime)
RUN mkdir -p backend/data/state

# Run as non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Health check for container orchestrators
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-5000}/health/live')"

# Railway/Render inject PORT; config.py reads it
CMD ["gunicorn", "-c", "gunicorn.conf.py", "backend.app:create_app()"]
