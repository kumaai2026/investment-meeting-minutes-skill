#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
export FUNASR_MODEL_CACHE="${FUNASR_MODEL_CACHE:-/Users/nananaranja/Documents/Codex/asr-model-cache}"
export MODELSCOPE_CACHE="${MODELSCOPE_CACHE:-${FUNASR_MODEL_CACHE}/modelscope}"
export HF_HOME="${HF_HOME:-${FUNASR_MODEL_CACHE}/huggingface}"
export FUNASR_NANO_PYTHON="${FUNASR_NANO_PYTHON:-/Users/nananaranja/Documents/会议纪要整理/.transcribe-venv/bin/python}"
export SENSEVOICE_BRIDGE_AUX_ENGINE="${SENSEVOICE_BRIDGE_AUX_ENGINE:-}"
export KUMAAI_SYNC_LOG_DIR="${KUMAAI_SYNC_LOG_DIR:-${HOME}/Library/Logs/kumaai-sync}"
export PATH="/Users/nananaranja/Documents/会议纪要整理/.transcribe-venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
LIBREOFFICE_LIBRARY_PATH="/opt/homebrew/opt/little-cms2/lib:/opt/homebrew/lib:/usr/local/opt/little-cms2/lib:/usr/local/lib"
export DYLD_FALLBACK_LIBRARY_PATH="${LIBREOFFICE_LIBRARY_PATH}:${DYLD_FALLBACK_LIBRARY_PATH:-}"
export DYLD_LIBRARY_PATH="${LIBREOFFICE_LIBRARY_PATH}:${DYLD_LIBRARY_PATH:-}"

exec "${FUNASR_NANO_PYTHON}" "${SCRIPT_DIR}/sensevoice_transcription_server.py"
