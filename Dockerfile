# Multi-stage build for smaller image size
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY setup.py .
COPY README.md .

# Make sure scripts are in PATH
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Install the package
RUN pip install --no-cache-dir -e .

# Create directory for reports
RUN mkdir -p /app/reports

# Set the entrypoint
ENTRYPOINT ["python", "scripts/generate_report.py"]
