# Python 3.13 - latest stable (Django 6.0 supports 3.12, 3.13, 3.14)
FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
# Use --ignore-installed to handle django-celery version constraints with Django 6.0
RUN pip install --no-cache-dir -r requirements.txt || \
    pip install --no-cache-dir --ignore-installed -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "reddit_analyzer.wsgi:application", "--bind", "0.0.0.0:8000"]
