FROM python:3.14-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# Copy application code.
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
