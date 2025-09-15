# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config

# Expose port for tagging service
EXPOSE 8000

# Support both aggregator CLI and tagging service
# Use environment variable SERVICE_MODE to determine which to run
# Default to aggregator CLI for backward compatibility
COPY entrypoint.sh ./
RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
CMD ["aggregator"]


