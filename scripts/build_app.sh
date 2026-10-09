#!/bin/sh
# Build dist/oktoboot.app and the release zip (Apple Silicon, macOS 15+).
# Needs the data built first: scripts/build_frequencies.py, scripts/build_doda.py
set -e
cd "$(dirname "$0")/.."
VERSION=$(PYTHONPATH=src .venv/bin/python -c "import oktoboot; print(oktoboot.__version__)")
PYTHONPATH=src .venv/bin/python -m PyInstaller oktoboot.spec --noconfirm --log-level WARN
dist/oktoboot.app/Contents/MacOS/oktoboot --selftest
ZIP="dist/oktoboot-$VERSION-macos-arm64.zip"
rm -f "$ZIP"
ditto -c -k --keepParent dist/oktoboot.app "$ZIP"
shasum -a 256 "$ZIP"
