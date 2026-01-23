# Dockerfile for NHS Manage Breast Screening Gateway - PACS Server
FROM python:3.14-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for package management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create working directory
WORKDIR /app

# Create PACS storage directories
RUN mkdir -p /var/lib/pacs/storage /var/log/pacs

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Set environment variables with defaults
ENV PACS_AET=SCREENING_PACS \
    PACS_PORT=4244 \
    PACS_STORAGE_PATH=/var/lib/pacs/storage \
    PACS_DB_PATH=/var/lib/pacs/pacs.db \
    LOG_LEVEL=INFO \
    PYTHONPATH=/app/src

# Expose DICOM port
EXPOSE 4244

# Run the PACS server
CMD ["uv", "run", "python", "-m", "server"]
