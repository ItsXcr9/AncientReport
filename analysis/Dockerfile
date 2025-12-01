FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Set environment variables
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 8800

# Run the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8800"]
