#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Canto → Mando Blueprint — Launcher
# Starts the combined server on port 8800 and opens the browser.
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_SHARED_VENV="$HOME/Virtual Envs/Canto_Mando_App"
LEGACY_VENV_DIR="$PROJECT_DIR/.venv"
PORT=8800

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Canto → Mando Blueprint"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Kill any existing process on port 8800
if lsof -ti:"$PORT" &>/dev/null; then
  echo "  Stopping existing server on port $PORT…"
  lsof -ti:"$PORT" | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

# Pick Python: prefer an explicit override, then the shared venv, then legacy .venv.
VENV_DIR="${CANTO_MANDO_VENV:-}"
if [[ -z "$VENV_DIR" && -d "$DEFAULT_SHARED_VENV" ]]; then
  VENV_DIR="$DEFAULT_SHARED_VENV"
fi
if [[ -z "$VENV_DIR" && -d "$LEGACY_VENV_DIR" ]]; then
  VENV_DIR="$LEGACY_VENV_DIR"
fi

PYTHON="${VENV_DIR:+$VENV_DIR/bin/python3}"
if [[ -z "$PYTHON" || ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
  echo "  ⚠ No project venv found — using system Python: $PYTHON"
else
  echo "  Using project venv: $VENV_DIR"
fi

# Start server in background
cd "$SCRIPT_DIR"
echo "  Starting server on http://localhost:$PORT …"
"$PYTHON" server.py &
SERVER_PID=$!

# Wait for server to be ready
for i in {1..15}; do
  if curl -s "http://localhost:$PORT" &>/dev/null; then
    break
  fi
  sleep 0.4
done

echo "  ✅ Ready  →  http://localhost:$PORT"
echo "  Press Ctrl+C to stop."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Open browser (macOS)
if command -v open &>/dev/null; then
  open "http://localhost:$PORT"
fi

# Keep foreground — SIGINT cleanly stops the server
wait "$SERVER_PID"
