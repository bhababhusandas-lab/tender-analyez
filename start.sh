#!/bin/bash
set -e

echo "🚀 Starting Unique Type Team..."
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "❌ Python 3 not found. Please install Python 3.11+"
  exit 1
fi

# Check Node
if ! command -v node &>/dev/null; then
  echo "❌ Node.js not found. Please install Node.js 18+"
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- Backend ---
echo "⚙️  Setting up backend..."
cd "$PROJECT_DIR/backend"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "   Virtual environment created."
fi

source .venv/bin/activate
pip install -q -r requirements.txt
echo "   Backend dependencies installed."

# Start backend in background — port 8001 to match the frontend's Vite proxy
# (frontend/vite.config.ts proxies /api → http://localhost:8001). Using 8000
# here would leave the frontend unable to reach the API, so login would fail.
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload &
BACKEND_PID=$!
echo "   Backend running on http://localhost:8001 (PID: $BACKEND_PID)"

# --- Frontend ---
echo ""
echo "🎨  Setting up frontend..."
cd "$PROJECT_DIR/frontend"

if [ ! -d "node_modules" ]; then
  npm install --silent
  echo "   Frontend dependencies installed."
fi

echo "   Frontend running on http://localhost:3000"
echo ""
echo "✅  Unique Type is ready!"
echo "   Open: http://localhost:3000"
echo ""
echo "   Press Ctrl+C to stop."
echo ""

# Start frontend (foreground)
npm run dev

# Cleanup backend on exit
kill $BACKEND_PID 2>/dev/null
