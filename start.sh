#!/bin/bash

# The AI Counsel - Start script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load ports (and anything else) from the root .env without clobbering values
# already exported in the environment.
if [ -f "$SCRIPT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$SCRIPT_DIR/.env"
  set +a
fi

export PORT_BACKEND="${PORT_BACKEND:-8001}"
export PORT_FRONTEND="${PORT_FRONTEND:-5173}"

BACKEND_URL="http://localhost:${PORT_BACKEND}"
FRONTEND_URL="http://localhost:${PORT_FRONTEND}"

open_browser() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  else
    echo "Open $url in your browser"
  fi
}

echo "Starting The AI Counsel..."
echo ""

# Start backend
echo "Starting backend on $BACKEND_URL..."
LLM_COUNCIL_BIND_HOST="${LLM_COUNCIL_BIND_HOST:-0.0.0.0}" PORT_BACKEND="$PORT_BACKEND" uv run python -m backend.main &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 2

# Start frontend
echo "Starting frontend on $FRONTEND_URL..."
cd frontend
npm run dev -- --host --port "$PORT_FRONTEND" &
FRONTEND_PID=$!

# Wait for frontend to become ready, then open the default browser
echo "Waiting for frontend..."
for _ in $(seq 1 30); do
  if curl -sf "$FRONTEND_URL" >/dev/null 2>&1; then
    echo "Opening $FRONTEND_URL in your browser..."
    open_browser "$FRONTEND_URL"
    break
  fi
  sleep 1
done

echo ""
echo "✓ The AI Counsel is running!"
echo "  Backend:  $BACKEND_URL"
echo "  Frontend: $FRONTEND_URL"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
