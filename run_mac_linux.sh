#!/usr/bin/env bash
# SpendGuard AI one-click launcher for macOS and Linux.
# First run: creates a private Python environment (.venv) and installs the dependencies (a few minutes).
# Later runs: start straight away. Needs Python 3.10 or newer.
set -e
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required: https://www.python.org/downloads/"
  exit 1
fi

[ -f .env ] || cp .env.example .env
# pip does not read .env: take the proxy settings from it so installs work on a corporate network
while IFS='=' read -r key value; do
  case "$key" in HTTP_PROXY|HTTPS_PROXY|NO_PROXY|http_proxy|https_proxy|no_proxy) export "$key=$value" ;; esac
done < <(grep -E '^[A-Za-z_]+=' .env)

if [ ! -x .venv/bin/python ]; then
  echo "[1/3] Creating the Python environment..."
  "$PY" -m venv .venv
fi
# A venv whose creation was interrupted can lack pip; add it before installing.
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  echo "Adding pip to the Python environment..."
  .venv/bin/python -m ensurepip --upgrade --default-pip \
    || { echo "Could not add pip. On Debian/Ubuntu: sudo apt install python3-venv, then delete .venv and run again."; exit 1; }
fi
if [ ! -f .venv/installed.ok ]; then
  echo "[2/3] Installing dependencies, first run only..."
  .venv/bin/python -m pip install --disable-pip-version-check --timeout 30 --retries 2 -q -r requirements.txt
  echo ok > .venv/installed.ok
fi
export PORT="${PORT:-8000}" RELOAD=0
echo "[3/3] Starting SpendGuard AI at http://127.0.0.1:$PORT  (Ctrl+C to stop)"
( sleep 4; (open "http://127.0.0.1:$PORT" || xdg-open "http://127.0.0.1:$PORT") >/dev/null 2>&1 || true ) &
exec .venv/bin/python main.py
