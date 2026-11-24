#!/bin/bash
# Unique Type Backend — AWS startup script
# Run once after uploading: chmod +x start.sh && ./start.sh

set -e

echo "=== Installing dependencies ==="
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "=== Starting Unique Type API ==="
.venv/bin/gunicorn app.main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 300 \
  --access-logfile - \
  --error-logfile - \
  --daemon

echo "=== Server running on port 8000 ==="
echo "Test: curl http://localhost:8000/api/health"
