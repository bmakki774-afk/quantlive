# QuantLive Signal Platform â Dockerfile
# Python 3.11 slim â matches Railway's recommended base

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (psycopg2 needs libpq)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Railway sets PORT automatically â not needed for this app
# but good practice to expose it for health checks
EXPOSE 8080

# Start the scheduler
CMD ["python", "main.py"]
