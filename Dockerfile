# Multi-Agent Financial Intelligence System
# Standard single-stage Dockerfile to prevent pip wheel resolution errors
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required for some python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    libffi-dev \
    libssl-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install -r requirements.txt

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
EXPOSE 8000

# Default command - runs main app
CMD ["python", "main.py", "--daemon"]
