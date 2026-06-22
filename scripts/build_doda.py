#!/usr/bin/env python3
"""
Build doda.db from DODa (Darija Open Dataset) CSVs.

Source: https://github.com/darija-open-dataset/dataset
License: CC BY-NC 4.0

Schema of doda.db:
  darija(arabizi TEXT, arabic TEXT, english TEXT)
  INDEX on arabizi (lowercase)

Run:
  python3 scripts/build_doda.py
"""

import csv
import io
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "doda.db"

# DODa CSV folders to harvest
FOLDERS = [
    "semantic categories",
    "syntactic categories",
]
# sentences.csv has a different format (full sentences, not word pairs) — skip for now

REPO = "darija-open-dataset/dataset"


def list_csvs(folder: str) -> list[str]:
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{folder}", "--jq", ".[].name"],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().splitlines() if f.endswith(".csv")]


def fetch_csv(folder: str, filename: str) -> str:
    result = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{folder}/{filename}", "--jq", ".content"],
        capture_output=True, text=True
    )
    import base64
    return base64.b64decode(result.stdout.strip()).decode("utf-8")


def parse_csv(content: str, source: str) -> list[tuple[str, str, str]]:
    """
    Parse a DODa CSV. Columns: n1[, n2, n3...], darija_ar, eng
    Returns list of (arabizi_lower, arabic, english) tuples.
    """
    rows = []
    reader = csv.reader(io.StringIO(content))
    headers = next(reader, None)
    if not headers:
        return rows

    # Find darija_ar column index
    try:
        ar_idx = headers.index("darija_ar")
    except ValueError:
        print(f"  WARNING: no darija_ar column in {source}, headers: {headers}")
        return rows

    eng_idx = headers.index("eng") if "eng" in headers else None

    # Arabizi columns are everything before darija_ar
    arabizi_cols = list(range(ar_idx))

    for row in reader:
        if len(row) <= ar_idx:
            continue
        arabic = row[ar_idx].strip()
        if not arabic:
            continue
        english = row[eng_idx].strip() if eng_idx is not None and len(row) > eng_idx else ""

        for col_idx in arabizi_cols:
            if col_idx >= len(row):
                continue
            arabizi = row[col_idx].strip()
            if arabizi:
                rows.append((arabizi.lower(), arabic, english))

    return rows


def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE darija (
            arabizi TEXT NOT NULL,
            arabic  TEXT NOT NULL,
            english TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX idx_arabizi ON darija(arabizi)")

    total = 0
    for folder in FOLDERS:
        print(f"\nFolder: {folder}")
        csvs = list_csvs(folder)
        for fname in csvs:
            print(f"  {fname} ...", end=" ", flush=True)
            content = fetch_csv(folder, fname)
            rows = parse_csv(content, fname)
            conn.executemany(
                "INSERT INTO darija(arabizi, arabic, english) VALUES (?, ?, ?)",
                rows
            )
            print(f"{len(rows)} entries")
            total += len(rows)

    conn.commit()

    # De-duplicate: keep distinct (arabizi, arabic) pairs
    conn.execute("""
        DELETE FROM darija WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM darija GROUP BY arabizi, arabic
        )
    """)
    conn.commit()
    conn.execute("VACUUM")

    count = conn.execute("SELECT COUNT(*) FROM darija").fetchone()[0]
    conn.close()

    print(f"\nDone. {count} unique (arabizi, arabic) entries → {DB_PATH}")


if __name__ == "__main__":
    main()
