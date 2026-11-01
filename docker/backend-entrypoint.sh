#!/bin/sh
# Prepare the database, then start the backend. Safe to run on every start.
set -e
echo "Applying migrations..."
alembic upgrade head
python -m seed.ensure
echo "Starting the backend..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
