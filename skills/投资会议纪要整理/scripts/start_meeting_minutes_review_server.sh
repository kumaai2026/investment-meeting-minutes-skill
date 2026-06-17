#!/usr/bin/env bash
set -euo pipefail

REVIEW_SESSION_NAME="meeting_minutes_review"
FRONTEND_SESSION_NAME="kuma_frontend"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/Users/kumaai/Library/Logs/kumaai-sync"
OUT_LOG="${LOG_DIR}/meeting-minutes-review-server.out.log"
ERR_LOG="${LOG_DIR}/meeting-minutes-review-server.err.log"
FRONTEND_OUT_LOG="${LOG_DIR}/kuma-frontend-server.out.log"
FRONTEND_ERR_LOG="${LOG_DIR}/kuma-frontend-server.err.log"

mkdir -p "${LOG_DIR}"

LIBREOFFICE_LIBRARY_PATH="/opt/homebrew/opt/little-cms2/lib:/opt/homebrew/lib:/usr/local/opt/little-cms2/lib:/usr/local/lib"
export DYLD_FALLBACK_LIBRARY_PATH="${LIBREOFFICE_LIBRARY_PATH}:${DYLD_FALLBACK_LIBRARY_PATH:-}"
export DYLD_LIBRARY_PATH="${LIBREOFFICE_LIBRARY_PATH}:${DYLD_LIBRARY_PATH:-}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

if command -v screen >/dev/null 2>&1; then
  screen -S "${REVIEW_SESSION_NAME}" -X quit >/dev/null 2>&1 || true
  screen -S "${FRONTEND_SESSION_NAME}" -X quit >/dev/null 2>&1 || true
else
  echo "screen is required to keep the review server attached to a user session." >&2
  exit 1
fi

for port in 8767 4396 1000; do
  pid="$(lsof -tiTCP:${port} -sTCP:LISTEN -n -P || true)"
  if [[ -n "${pid}" ]]; then
    kill ${pid} >/dev/null 2>&1 || true
  fi
done
sleep 1

: > "${OUT_LOG}"
: > "${ERR_LOG}"
: > "${FRONTEND_OUT_LOG}"
: > "${FRONTEND_ERR_LOG}"

screen -dmS "${REVIEW_SESSION_NAME}" zsh -lc "cd '${SCRIPT_DIR}' && MEETING_REVIEW_BASE_URL='https://kuma.d91.global' /usr/bin/python3 meeting_minutes_review_server.py >> '${OUT_LOG}' 2>> '${ERR_LOG}'"
screen -dmS "${FRONTEND_SESSION_NAME}" zsh -lc "cd '${SCRIPT_DIR}' && MEETING_REVIEW_SERVER_PORT=1000 MEETING_REVIEW_BASE_URL='https://kuma.d91.global' /usr/bin/python3 meeting_minutes_review_server.py >> '${FRONTEND_OUT_LOG}' 2>> '${FRONTEND_ERR_LOG}'"

sleep 2
curl -fsS --max-time 5 http://127.0.0.1:8767/health
curl -fsS --max-time 5 http://127.0.0.1:1000/health
echo
