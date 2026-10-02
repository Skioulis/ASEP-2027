#!/bin/sh
set -e

echo "[entrypoint] Applying database migrations..."
flask db upgrade

echo "[entrypoint] Loading the question bank (skipped if already loaded)..."
flask seed

echo "[entrypoint] Ensuring the admin account..."
flask ensure-admin

echo "[entrypoint] Starting gunicorn..."
exec gunicorn --bind 0.0.0.0:8000 --workers "${WEB_CONCURRENCY:-3}" --threads "${GUNICORN_THREADS:-8}" \
    --timeout 60 --access-logfile - \
    --access-logformat '%({x-forwarded-for}i)s %(h)s "%(r)s" %(s)s %(b)s' app:app
