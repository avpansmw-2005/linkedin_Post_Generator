# Use lightweight official Python 3.11 slim image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging for real-time stdout in Azure
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies and standard TrueType fonts for Pillow card rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY agents/ /app/agents/
COPY integrations/ /app/integrations/
COPY orchestrator.py state.py main.py /app/

# Create persistent data directory for SQLite checkpointer and generated images
RUN mkdir -p /app/data/images

# Run as non-root user for container security hardening
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Set volume mount point for persistent storage
VOLUME ["/app/data"]

# Run the Telegram polling daemon and scheduler
CMD ["python", "main.py"]
