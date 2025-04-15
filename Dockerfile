FROM python:3.11-slim-buster

WORKDIR /app

# Install system dependencies, including tesseract-ocr
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code
COPY . .

# Set the entry point for your application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]