#!/bin/bash

# The AI Counsel - Start script

FRONTEND_URL="http://localhost:5173"

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
echo "Starting backend on http://localhost:8001..."
LLM_COUNCIL_BIND_HOST="${LLM_COUNCIL_BIND_HOST:-0.0.0.0}" uv run python -m backend.main &
BACKEND_PID=$!

# Wait a bit for backend to start
sleep 2

# Start frontend
echo "Starting frontend on http://localhost:5173..."
cd frontend
npm run dev -- --host &
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
echo "  Backend:  http://localhost:8001"
echo "  Frontend: $FRONTEND_URL"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
