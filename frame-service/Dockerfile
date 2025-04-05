FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY frame-service/requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt


# Copy the application code
# Copy the rest of the application
COPY frame-service/ /app/
COPY utils/ /app/

# Add the current directory to PYTHONPATH to find the utils module
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose the port
EXPOSE 5004

# Start the FastAPI app with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5004", "--reload"] 