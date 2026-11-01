# The backend (FastAPI + the agent). Used by docker-compose.app.yml.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv

# Exact versions from requirements.lock. Installed first, so rebuilding after a code change does not reinstall them
COPY requirements.lock .
RUN pip install -r requirements.lock

COPY alembic.ini .
COPY app app
COPY migrations migrations
COPY seed seed
COPY docker/backend-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=20 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/docs', timeout=2)"

ENTRYPOINT ["/entrypoint.sh"]
