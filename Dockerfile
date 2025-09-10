# Use Python 3.11 Alpine for minimal size
FROM python:3.11-alpine

# Install build dependencies for some Python packages
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    python3-dev \
    && rm -rf /var/cache/apk/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create data directory for database
RUN mkdir -p /app/data

# Create non-root user for security (but don't switch to it yet for testing)
RUN adduser -D -u 1000 chronotask && \
    chmod -R 777 /app/data

# For testing, run as root
# USER chronotask

# Expose HTTP API port
EXPOSE 8000

# Expose MCP port (if needed)
EXPOSE 8001

# Volume for persistent data
VOLUME ["/app/data"]

# Environment variables
ENV CHRONOTASK_DATABASE_URL=sqlite:////app/data/chronotask.db \
    CHRONOTASK_LOG_FILE=/app/data/chronotask.log \
    PYTHONUNBUFFERED=1

# Default command - run HTTP server
WORKDIR /app
CMD ["python", "-m", "src.main"]