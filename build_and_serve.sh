#!/bin/bash
# Build Angular and serve everything from Flask on :5000
# Usage: ./build_and_serve.sh
# Then: ngrok http 5000

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend/cognicap-app"
BACKEND_DIR="$ROOT_DIR/backend"

echo "==> Building Angular (development config — no budget limits)..."
cd "$FRONTEND_DIR"
npx ng build --configuration=development

echo ""
echo "==> Angular build complete."
echo "    Output: $FRONTEND_DIR/dist/cognicap-app/browser"
echo ""
echo "==> Starting Flask on port 5000..."
echo "    In another terminal, run: ngrok http 5000"
echo ""

cd "$BACKEND_DIR"
./venv/bin/python3 app.py
