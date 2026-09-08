#!/bin/sh
set -eu

# Fix data directory ownership so appuser can write settings/conversations.
# Docker creates the mounted ./data dir as root at runtime; this corrects it.
chown -R appuser:appgroup /app/data

CONFIG_FILE="${FRONTEND_DIST_DIR:-/app/frontend/dist}/config.js"
API_URL="${BACKEND_HOST:-}"

# JSON-encode $API_URL before interpolating into config.js. A raw interpolation
# would let any caller who controls $BACKEND_HOST inject arbitrary JavaScript
# into the file served to every browser client (stored XSS). python3 is
# guaranteed by the base image (nikolaik/python-nodejs).
API_URL_JSON=$(python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$API_URL")

cat > "$CONFIG_FILE" <<EOF
window.__AI_COUNSEL_CONFIG__ = {
  apiUrl: ${API_URL_JSON},
};
EOF

# Append the configured backend port to the uvicorn command. CMD omits --port so
# that PORT_BACKEND (from .env or the compose environment) can drive it at runtime.
case "$*" in
  *uvicorn*)
    if [ "${*#*--port}" = "$*" ]; then
      set -- "$@" --port "${PORT_BACKEND:-8001}"
    fi
    ;;
esac

exec gosu appuser "$@"
