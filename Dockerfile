# Use an official Python image
FROM python:3.11-slim

# Install system dependencies (including tesseract)
RUN apt-get update && \
    apt-get install -y tesseract-ocr libgl1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy code and install Python deps
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 5000

# Run the app
CMD ["python", "app.py"]
