#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Seeding platform policy library..."
python scripts/seed_policy_library.py

echo "Starting RAI Gateway..."
exec python -m uvicorn rai_gateway.main:app --host 0.0.0.0 --port 8000
