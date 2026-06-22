#!/usr/bin/env python3
"""
Build frequencies.db from hermitdave/FrequencyWords OpenSubtitles 2018 Arabic list.

Source: https://github.com/hermitdave/FrequencyWords
License: CC BY-SA 3.0

Also fetches Amiri font (SIL OFL).

Run:
  python3 scripts/build_frequencies.py
"""

import sqlite3
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "frequencies.db"
FONT_DIR = ROOT / "data" / "fonts"

FREQ_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
    "master/content/2018/ar/ar_full.txt"
)

AMIRI_URLS = {
    "Amiri-Regular.ttf": (
        "https://github.com/aliftype/amiri/releases/download/1.000/"
        "Amiri-1.000.zip"
    ),
}
# We'll fetch from the releases zip; fallback to direct file URLs
AMIRI_DIRECT = {
    "Amiri-Regular.ttf":
        "https://github.com/aliftype/amiri/raw/main/fonts/Amiri-Regular.ttf",
    "Amiri-Bold.ttf":
        "https://github.com/aliftype/amiri/raw/main/fonts/Amiri-Bold.ttf",
}


def build_frequencies():
    print(f"Fetching {FREQ_URL} ...")
    with urllib.request.urlopen(FREQ_URL, timeout=60) as resp:
        raw = resp.read().decode("utf-8")

    lines = raw.strip().splitlines()
    print(f"  {len(lines)} lines")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE frequencies (
            word      TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL
        )
    """)

    batch = []
    skipped = 0
    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            skipped += 1
            continue
        word, freq_str = parts
        word = word.strip()
        if not word:
            skipped += 1
            continue
        try:
            freq = int(freq_str)
        except ValueError:
            skipped += 1
            continue
        batch.append((word, freq))

    conn.executemany(
        "INSERT OR IGNORE INTO frequencies(word, frequency) VALUES (?, ?)",
        batch
    )
    conn.execute("CREATE INDEX idx_word ON frequencies(word)")
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM frequencies").fetchone()[0]
    conn.close()
    print(f"  {count} words inserted, {skipped} skipped → {DB_PATH}")


def fetch_fonts():
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for fname, url in AMIRI_DIRECT.items():
        dest = FONT_DIR / fname
        if dest.exists():
            print(f"  {fname} already present, skipping")
            continue
        print(f"Fetching {fname} ...")
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                dest.write_bytes(resp.read())
            print(f"  → {dest}")
        except Exception as e:
            print(f"  WARNING: failed to fetch {fname}: {e}")


def main():
    build_frequencies()
    fetch_fonts()
    print("\nDone.")


if __name__ == "__main__":
    main()
