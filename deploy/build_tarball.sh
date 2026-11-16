#!/bin/bash
# Build gold-app-v<version>-deploy.tar.gz at the repo root.
# Code paths only — no data/ (the journal lives server-side), no caches.
set -eu
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VERSION=$(python3 -c "import sys; sys.path.insert(0, '$ROOT'); from gold_app import __version__; print(__version__)")
OUT="$ROOT/gold-app-v$VERSION-deploy.tar.gz"
cd "$ROOT"
tar --exclude='__pycache__' --exclude='*.pyc' \
  -czf "$OUT" gold_app dashboard tests deploy events.json run.sh README.md RESEARCH_AND_DESIGN.md
echo "$OUT"
sha256sum "$OUT"
