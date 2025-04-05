# Use Python 3.10 slim image as base
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for OpenCV and other packages
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY ai-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt


# Copy the rest of the application
COPY ai-service/ /app/
COPY utils/ /app/

# Add the current directory to PYTHONPATH to find the utils module
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Set environment variables to ensure PyTorch uses CPU
ENV CUDA_VISIBLE_DEVICES=""
ENV FORCE_CPU=1

# Run the application
CMD ["python", "main.py"]
