# Quiz Bot Pro - Production Dockerfile
# Multi-stage build for smaller image

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /app/wheels -r requirements.txt


# Production stage
FROM python:3.11-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r botuser && useradd -r -g botuser botuser

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels and install
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

# Copy application
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create directories
RUN mkdir -p /app/logs /app/audio/cache && \
    chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import asyncio; from src.core.redis import get_redis; asyncio.run(get_redis())" || exit 1

# Run
CMD ["python", "-m", "src.bot"]
