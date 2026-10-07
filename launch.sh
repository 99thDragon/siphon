#!/usr/bin/env bash
# SIPHON - start the downloader. macOS and Linux; Windows users run launch.bat.
set -u
cd "$(dirname "$0")"

PY=""
for c in python3 python; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -n "$PY" ] || {
  echo
  echo "  Python 3 is not installed."
  echo "  macOS:  brew install python"
  echo "  Linux:  sudo apt install python3 python3-pip"
  echo
  exit 1
}

# yt-dlp is the one hard dependency; ffmpeg is checked in the UI's health row.
"$PY" -c 'import yt_dlp' 2>/dev/null || {
  echo "  Installing yt-dlp..."
  "$PY" -m pip install --quiet --upgrade yt-dlp \
    || "$PY" -m pip install --quiet --upgrade --break-system-packages yt-dlp \
    || { echo "  Could not install yt-dlp. Try: $PY -m pip install yt-dlp"; exit 1; }
}

exec "$PY" server.py
