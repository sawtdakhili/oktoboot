"""
Persistent learned-choices store.
Lives at ~/.local/share/oktoboot/learned.db (XDG) or ~/Library/... on macOS.
"""

import platform
import sqlite3
from pathlib import Path

from oktoboot.engine import record_choice


def _db_path() -> Path:
    if platform.system() == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "oktoboot"
    else:
        xdg = Path.home() / ".local" / "share"
        base = xdg / "oktoboot"
    base.mkdir(parents=True, exist_ok=True)
    return base / "learned.db"


def open_learned_db() -> sqlite3.Connection:
    path = _db_path()
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS choices (
            input     TEXT NOT NULL,
            chosen    TEXT NOT NULL,
            count     INTEGER DEFAULT 1,
            last_used INTEGER,
            PRIMARY KEY (input, chosen)
        )
    """)
    conn.commit()
    return conn
