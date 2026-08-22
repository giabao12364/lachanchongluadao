#!/bin/bash
set -e

echo "[entrypoint] Lachan FastAPI starting..."
echo "[entrypoint] Waiting for PostgreSQL (db:5432)..."

DB_HOST="db"
DB_PORT="5432"
for i in {1..30}; do
  if (echo > /dev/tcp/$DB_HOST/$DB_PORT) >/dev/null 2>&1; then
    echo "[entrypoint] PostgreSQL is UP (after $i tries)"
    break
  fi
  echo "[entrypoint]   try $i/30: waiting for DB..."
  sleep 1
done

echo "[entrypoint] Waiting for Redis (redis:6379)..."
for i in {1..15}; do
  if (echo > /dev/tcp/redis/6379) >/dev/null 2>&1; then
    echo "[entrypoint] Redis is UP (after $i tries)"
    break
  fi
  echo "[entrypoint]   try $i/15: waiting for Redis..."
  sleep 1
done

echo "[entrypoint] Running init_db.py (create tables + seed data if empty)..."
python /app/init_db.py || echo "[entrypoint] Warning: init_db.py failed, continue anyway"

echo "[entrypoint] Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level info
