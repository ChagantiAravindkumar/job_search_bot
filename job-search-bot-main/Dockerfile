FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all code files and frontend assets
COPY . .

# Expose port 8050
EXPOSE 8050

# Start the FastAPI server using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050"]
