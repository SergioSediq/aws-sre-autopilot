#!/usr/bin/env python3
"""Package sre-brain Lambda for deployment. Cross-platform."""
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "sre-brain" / "handler.py"
OUT = ROOT / "dist"
ZIP_NAME = "sre-brain-handler.zip"

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    zip_path = OUT / ZIP_NAME
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(SRC, "handler.py")
    print(f"Built: {zip_path}")

if __name__ == "__main__":
    main()
