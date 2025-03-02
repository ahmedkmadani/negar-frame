# Use Python 3.9 slim image as base
FROM python:3.9-slim

# Set working directory in container
WORKDIR /app

# Install dependencies first (this layer will be cached)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Don't copy the code - it will be mounted
# COPY . .

# Create directory for frames
RUN mkdir -p static/frames

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV EVENTLET_NO_GREENDNS=yes

# Expose the port the app runs on
EXPOSE 5003

# Use Flask development server with auto-reload
CMD ["python", "main.py"]