FROM python:3.12-slim

# Set environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose API and Mock server ports
EXPOSE 8000 8001

# Healthcheck
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default entrypoint starts main IncuBrix distribution API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
