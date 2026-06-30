# Multi-Agent Financial Intelligence System
# Multi-stage Dockerfile for containerized deployment

# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system build dependencies required for compiling wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Create wheels for all dependencies to avoid compiling in the final stage
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt


# --- Stage 2: Final Runtime ---
FROM python:3.11-slim

WORKDIR /app

# Install minimal runtime dependencies (e.g. curl for docker healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from the builder stage
COPY --from=builder /build/wheels /wheels

# Install packages from the pre-compiled wheels
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application source code
COPY . .

# Create necessary directories
RUN mkdir -p data logs /tmp/chroma_db

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV USE_REDIS=true
ENV USE_CHROMADB=true
ENV USE_INFLUXDB=true

# Expose ports
# 8000: Dashboard API
EXPOSE 8000

# Default command - runs main app
CMD ["python", "main.py", "--daemon"]
