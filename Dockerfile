FROM python:3.11.12-slim

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

# Bake the current DB as a seed snapshot.
# On first boot start.sh copies this to the persistent volume at /data/runcoach.db.
# Subsequent boots skip the copy and use the live volume DB.
COPY runcoach.db ./runcoach.db.seed

# Startup script — handles volume seeding then launches uvicorn
COPY start.sh ./start.sh

# Create non-root user for security
RUN useradd --create-home appuser && \
    chown -R appuser:appuser /app && \
    chmod +x /app/start.sh

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run via startup script so the volume is seeded before uvicorn starts
CMD ["/app/start.sh"]
