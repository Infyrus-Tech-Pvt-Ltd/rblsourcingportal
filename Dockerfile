# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt ./

# Install dependencies if requirements.txt exists
RUN pip install --no-cache-dir -r requirements.txt || true

# Copy the rest of the application files
COPY . .

# Expose the required ports
EXPOSE 8090
EXPOSE 5050

# Run the app
CMD ["python", "runner.py"]
