#!/bin/bash
# Package sre-brain Lambda for deployment
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="$ROOT/dist"
ZIP_NAME="sre-brain-handler.zip"

mkdir -p "$OUT"
cd "$ROOT/sre-brain"
zip -r "$OUT/$ZIP_NAME" handler.py
echo "Built: $OUT/$ZIP_NAME"
