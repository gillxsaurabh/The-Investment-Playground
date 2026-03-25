# Stage 1: Build Angular frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend/cognicap-app
COPY frontend/cognicap-app/package*.json ./
RUN npm ci
COPY frontend/cognicap-app/ ./
RUN npx ng build --configuration=development

# Stage 2: Python runtime
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies (bump DEPS_VER to bust Railway's layer cache)
ARG DEPS_VER=2
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy Angular build output from Stage 1
COPY --from=frontend-builder /app/frontend/cognicap-app/dist ./frontend/cognicap-app/dist

# Create state directory (gitignored — must exist at runtime)
RUN mkdir -p backend/data/state

# Railway/Render inject PORT; config.py reads it
CMD ["python", "backend/app.py"]
