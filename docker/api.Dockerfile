# syntax=docker/dockerfile:1
# API image: Flask app served by gunicorn. Build from the repository root:
#   docker build -f docker/api.Dockerfile .
FROM python:3.14-slim@sha256:35caba83af2fe6da9a5d922f9b0156f21d1246a48278c58a08bd253303ba42e8

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Only nginx reaches the API in this image, and it overwrites X-Real-IP (D-025).
ENV TRUST_PROXY_HEADER=1

COPY requirements.txt requirements-deploy.txt /app/
RUN pip install --no-cache-dir -r /app/requirements-deploy.txt \
    && useradd --system --uid 10001 --no-create-home app

COPY api/ /app/api/
# The importer republishes the entity dictionary and the API writes logs; nothing else is writable.
RUN mkdir /app/logs && chown app /app/logs /app/api/dictionary /app/api/dictionary/entities.json

WORKDIR /app/api
USER app
EXPOSE 5000
# Liveness only: the port accepts connections. It does not prove the graph is imported.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4)"]
# One worker: the log files rotate per process (see README, Logging).
# Critical only (BUG-003): when the 30 s watchdog kills a stuck worker, Gunicorn logs "Error handling request"
# with the URL, which holds the question, at error level. Its "WORKER TIMEOUT" line is critical and has no URL.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--log-level", "critical", "main:create_app()"]
