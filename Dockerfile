# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set working directory in container
WORKDIR /app

# Install system dependencies required for Pillow
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create directory for frames
RUN mkdir -p static/frames

# Expose the port the app runs on
EXPOSE 5003

# Command to run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5003", "--workers", "4", "main:app"] 