FROM python:3.9-slim

WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install dependencies
RUN pip install -r requirements.txt

# Environment variables
ENV PYTHONUNBUFFERED=1

# Expose the port
EXPOSE 5004

# Start the FastAPI app with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5004", "--reload"] 