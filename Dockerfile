# Multi-stage production container for MotionFence Judge Console & API Server (Phase 2Q)
# Build Stage: Compile and optimize the Vite + React TypeScript Judge Console
FROM node:20-alpine AS frontend-builder

WORKDIR /app/console

# Install dependencies deterministically
COPY console/package*.json ./
RUN npm ci

# Copy frontend source code and compile production SPA bundle
COPY console/ ./
RUN npm run build

# Runtime Stage: Hardened, minimal Python 3.12 production runtime
FROM python:3.12-slim AS runtime

LABEL maintainer="MotionFence Engineering"
LABEL description="Deterministic runtime authorization layer for AI-generated physical actions"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PORT=8080 \
    HOST=0.0.0.0

# Install minimal OS dependencies and security updates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged system user for zero-privilege container execution
RUN useradd -m -u 10001 -s /bin/bash motionfence

WORKDIR /app

# Install Python runtime dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
COPY pyproject.toml README.md /app/
RUN pip install --no-cache-dir pydantic>=2.6.0 openai>=1.12.0 && pip install --no-cache-dir --no-deps -e .

# Copy application code and console server
COPY motionfence /app/motionfence
COPY scripts /app/scripts

# Copy compiled static assets from the frontend build stage
COPY --from=frontend-builder /app/console/dist /app/console/dist

# Secure ownership to non-root user
RUN chown -R motionfence:motionfence /app

USER motionfence

EXPOSE 8080

# Production Healthcheck against the strictly read-only health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=4).getcode() == 200 else 1)"

# Strictly read-only entrypoint with ZERO actuator or ticket minting authority
ENTRYPOINT ["python", "scripts/console_server.py", "--host", "0.0.0.0", "--port", "8080"]
