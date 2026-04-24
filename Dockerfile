FROM python:3.11.12-slim@sha256:dbf1de478a55d6763afaa39c2f3d7b54b25230614980276de5cacdde79529d0c

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (including data directory)
COPY app/ ./app/

# Copy Alembic migration config and scripts
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

# Startup script — runs Alembic migrations then launches uvicorn
COPY start.sh ./start.sh

# Create non-root user, prepare directories with restrictive permissions
RUN useradd --create-home appuser && \
    mkdir -p /data/pdf_cache && \
    chown -R appuser:appuser /app /data /data/pdf_cache && \
    chmod 700 /data/pdf_cache && \
    chmod +x /app/start.sh

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run via startup script
CMD ["/app/start.sh"]
