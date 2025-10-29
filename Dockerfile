# Multi-stage build for Box to Google Earth Pipeline

FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
  build-essential \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Install packages system-wide - copy requirements.txt and install  
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir -r /tmp/requirements.txt && \
  rm /tmp/requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY test_data/ ./test_data/

# Create directories for logs and output
RUN mkdir -p /app/logs /app/output

# Set Python path
ENV PYTHONPATH=/app

# Default command (override in docker-compose)
CMD ["python3", "-m", "src.main", "--once"]

