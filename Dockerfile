# Knowledge Ingestor Docker Image
# Multi-stage build for optimized production image with enhanced security and performance

# =============================================================================
# Build Stage - Compile dependencies and build application
# =============================================================================
FROM python:3.11-slim as builder

# Install system dependencies for building (including tesseract for OCR)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    pkg-config \
    libffi-dev \
    libssl-dev \
    tesseract-ocr \
    tesseract-ocr-eng \
    libtesseract-dev \
    poppler-utils \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install UV package manager for fast dependency resolution
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
COPY pyproject.toml uv.lock ./

# Create virtual environment and install dependencies
RUN uv venv --seed && \
    uv sync --frozen --no-dev

# Copy source code
COPY src/ ./src/
COPY README.md ./
COPY configs/ ./configs/

# Build wheel package
RUN uv build

# =============================================================================
# Production Stage - Minimal runtime image
# =============================================================================
FROM python:3.11-slim as production

# Install runtime system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libmagic1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user with specific UID/GID for security
RUN groupadd --gid 1000 ingestor && \
    useradd --create-home --shell /bin/bash --uid 1000 --gid 1000 ingestor

# Install UV in production image
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/dist/*.whl ./

# Activate virtual environment
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install the application wheel
RUN pip install --no-deps knowledge_ingestor-*.whl

# Create application directories with proper permissions
RUN mkdir -p /app/data /app/configs /app/logs /app/temp /app/cache && \
    chown -R ingestor:ingestor /app

# Copy configuration files
COPY --chown=ingestor:ingestor configs/ /app/configs/

# Switch to non-root user
USER ingestor

# Set environment variables for optimal Python performance
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONHASHSEED=random
ENV LOG_LEVEL=INFO
ENV DATA_DIR=/app/data
ENV CONFIG_DIR=/app/configs
ENV TEMP_DIR=/app/temp
ENV CACHE_DIR=/app/cache

# Expose port (FastAPI default)
EXPOSE 8000

# Health check with proper error handling
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=5)" || exit 1

# Default command - can be overridden
CMD ["uvicorn", "knowledge_ingestor.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Development Stage - Full development environment
# =============================================================================
FROM builder as development

# Install development dependencies
RUN uv sync --frozen

# Install additional development tools
RUN apt-get update && apt-get install -y \
    vim \
    less \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create directories
RUN mkdir -p /app/data /app/configs /app/logs /app/temp /app/cache

# Copy source code for development
COPY --chown=root:root . /app/

# Set development environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV LOG_LEVEL=DEBUG
ENV DEVELOPMENT=true

# Development health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=2 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health', timeout=3)" || exit 1

# Default development command with hot reloading
CMD ["uvicorn", "knowledge_ingestor.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src"]

# =============================================================================
# Worker Stage - Background task processing
# =============================================================================
FROM production as worker

# Switch back to root to install additional worker dependencies
USER root
RUN apt-get update && apt-get install -y \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Switch back to non-root user
USER ingestor

# Worker-specific environment variables
ENV WORKER_CONCURRENCY=4
ENV WORKER_PREFETCH=1
ENV REDIS_URL=redis://redis:6379/0

# Health check for worker
HEALTHCHECK --interval=60s --timeout=30s --start-period=30s --retries=3 \
    CMD python -c "import redis; r = redis.from_url('$REDIS_URL'); r.ping()" || exit 1

# Default worker command
CMD ["python", "-m", "knowledge_ingestor.worker"]

# =============================================================================
# Metadata and Documentation
# =============================================================================
LABEL maintainer="gyasis@gmail.com" \
      version="0.1.0" \
      description="Knowledge Ingestor - Document ingestion and storage system" \
      org.opencontainers.image.title="Knowledge Ingestor" \
      org.opencontainers.image.description="A modular document ingestion and storage system" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/gyasis/knowledge-ingestor" \
      org.opencontainers.image.licenses="MIT"