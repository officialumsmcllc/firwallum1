# OFFICIALUM1 — High-Performance Cloud Container for Render
FROM python:3.11-slim

# Avoid buffering Python logs in container output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Expose default port (Render will override via $PORT)
EXPOSE 8088

# Launch Server Orchestrator
CMD ["python", "server.py"]
