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

# Pinned to exact commits so two builds always produce the same data (and so
# the same rankings). To update a source, bump its commit and record why in
# DECISIONS.md.
FREQ_COMMIT = "525f9b560de45753a5ea01069454e72e9aa541c6"   # 2022-02-07
AMIRI_COMMIT = "6331fc82b0d20d9439a0792e21a9294ca015a93f"  # 2026-04-25

FREQ_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
    f"{FREQ_COMMIT}/content/2018/ar/ar_full.txt"
)

AMIRI_DIRECT = {
    "Amiri-Regular.ttf":
        f"https://github.com/aliftype/amiri/raw/{AMIRI_COMMIT}/fonts/Amiri-Regular.ttf",
    "Amiri-Bold.ttf":
        f"https://github.com/aliftype/amiri/raw/{AMIRI_COMMIT}/fonts/Amiri-Bold.ttf",
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
    # WITHOUT ROWID: the table is stored as its primary-key index, so the
    # word lookup needs no second copy of every word. (The old layout plus an
    # extra idx_word index stored each word three times — ~180 MB vs ~60 MB.)
    conn.execute("""
        CREATE TABLE frequencies (
            word      TEXT PRIMARY KEY,
            frequency INTEGER NOT NULL
        ) WITHOUT ROWID
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
    conn.commit()
    conn.execute("VACUUM")

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
