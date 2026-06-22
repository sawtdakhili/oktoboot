"""
Transliteration engine — three tiers:

  Tier 1: DODa direct lookup  → exact Darija words
  Tier 2: Generative + frequency filter  → MSA and novel words
  Tier 3: Learned preferences  → user's own persistent choices

Result: list of (arabic, score) sorted best-first.
Item 0 of the suggestion list is always the raw Latin input (handled by caller).
"""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent.parent / "data"
DODA_DB = DATA_DIR / "doda.db"
FREQ_DB = DATA_DIR / "frequencies.db"


# ---------------------------------------------------------------------------
# Phonetic mapping  (our own, Moroccan-first)
# ---------------------------------------------------------------------------
# Each key maps to an ordered list of Arabic letters.
# The ORDER matters: first = highest base probability.
# Keys are matched longest-first at each position.

MAPPING: dict[str, list[str]] = {
    # numbers
    "2":  ["أ", "إ", "ء", "آ", "ؤ", "ئ"],
    "3":  ["ع"],
    "3'": ["غ"],
    "5":  ["خ"],   # lower rank than kh
    "6":  ["ط"],
    "6'": ["ظ"],
    "7":  ["ح"],
    "7'": ["خ"],
    "8":  ["ه"],
    "9":  ["ق", "ص"],   # Moroccan: 9 = ق primary
    "9'": ["ض"],

    # digraphs — must come before single letters
    "ch": ["ش"],        # Moroccan-first (over sh)
    "sh": ["ش"],
    "gh": ["غ"],
    "kh": ["خ"],        # higher rank than 5
    "dh": ["ذ", "ظ"],
    "dj": ["ج"],        # Algerian/Tunisian; j is primary Moroccan
    "th": ["ث", "ذ"],

    # consonants
    "b":  ["ب"],
    "c":  ["ك", "س"],
    "d":  ["د", "ض"],
    "f":  ["ف"],
    "g":  ["ڭ", "ج", "ق", "ك"],   # ڭ = Moroccan /g/
    "h":  ["ه", "ح"],
    "j":  ["ج"],        # Moroccan primary
    "k":  ["ك"],
    "l":  ["ل"],
    "m":  ["م"],
    "n":  ["ن"],
    "p":  ["ب", "پ"],
    "q":  ["ق"],
    "r":  ["ر"],
    "s":  ["س", "ص"],
    "t":  ["ت", "ط"],
    "v":  ["ڤ", "ف"],
    "w":  ["و"],
    "x":  ["ز", "كس"],
    "y":  ["ي"],
    "z":  ["ز", "ذ", "ظ"],   # ز primary, ذ/ظ lower-ranked alternatives

    # vowels / semi-vowels
    "a":  ["ا", "أ"],
    "e":  ["ي", "ا", "ه", "ة"],
    "i":  ["ي", "ا"],
    "o":  ["و", "أ"],
    "u":  ["و", "أ"],

    # digraph vowels
    "ou": ["و"],
    "oo": ["و"],
    "ee": ["ي"],
    "ai": ["ي"],
    "ei": ["ي"],
    "aa": ["ا", "عا"],

    # apostrophe mid-word → hamza/ayn
    "'":  ["ع", "ء"],
}

# ---------------------------------------------------------------------------
# Expand mapping: add {consonant_key}{vowel} → same output (harakaat trick).
# This lets "min" → من, "salam" → سلم/سلام, etc.
# Arabic vowel letters (ا و ي) are NOT expanded — they're distinct letters.
# ---------------------------------------------------------------------------

_VOWELS = ("a", "e", "i", "o", "u")
_VOWEL_LETTERS = {"a", "e", "i", "o", "u"}

_EXPANDED: dict[str, list[str]] = dict(MAPPING)
for _key, _letters in list(MAPPING.items()):
    # Only expand consonant keys (keys that don't themselves start with a vowel)
    if _key[0] not in _VOWEL_LETTERS and _key not in ("ch", "sh", "gh", "kh", "dh", "dj", "th", "3'", "6'", "7'", "9'"):
        for _v in _VOWELS:
            _new_key = _key + _v
            if _new_key not in _EXPANDED:
                _EXPANDED[_new_key] = _letters

# For digraphs too
for _key in ("ch", "sh", "gh", "kh", "dh", "dj", "th"):
    _letters = MAPPING[_key]
    for _v in _VOWELS:
        _new_key = _key + _v
        if _new_key not in _EXPANDED:
            _EXPANDED[_new_key] = _letters

# Pre-sort: longest keys first so we match greedily
_SORTED_KEYS = sorted(_EXPANDED.keys(), key=len, reverse=True)

# ---------------------------------------------------------------------------
# URL / number pattern — words matching these bypass transliteration
# ---------------------------------------------------------------------------
_BYPASS_RE = re.compile(
    r"^("
    r"https?://"              # URL
    r"|www\."                 # URL
    r"|[0-9]+$"               # pure number → keep as-is (show Arabic-Indic as 2nd option)
    r")",
    re.IGNORECASE,
)

_ARABIC_INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")


# ---------------------------------------------------------------------------
# Database connections (lazy singletons)
# ---------------------------------------------------------------------------

_doda_conn: sqlite3.Connection | None = None
_freq_conn: sqlite3.Connection | None = None


def _doda() -> sqlite3.Connection:
    global _doda_conn
    if _doda_conn is None:
        _doda_conn = sqlite3.connect(str(DODA_DB), check_same_thread=False)
        _doda_conn.row_factory = sqlite3.Row
    return _doda_conn


def _freq() -> sqlite3.Connection:
    global _freq_conn
    if _freq_conn is None:
        _freq_conn = sqlite3.connect(str(FREQ_DB), check_same_thread=False)
        _freq_conn.row_factory = sqlite3.Row
    return _freq_conn


# ---------------------------------------------------------------------------
# Built-in Moroccan Darija overrides (supplements DODa for common words)
# These take priority over generative results.
# ---------------------------------------------------------------------------

_DARIJA_OVERRIDES: dict[str, list[str]] = {
    "labaas":   ["لاباس"],
    "labes":    ["لاباس"],
    "wach":     ["واش"],
    "wach":     ["واش"],
    "nta":      ["نتا"],
    "nti":      ["نتي"],
    "hna":      ["حنا"],
    "ntoma":    ["نتوما"],
    "homa":     ["هوما"],
    "daba":     ["دابا"],
    "gadi":     ["غادي"],
    "kayn":     ["كاين"],
    "makaynch": ["ماكاينش"],
    "makainch": ["ماكاينش"],
    "bghit":    ["بغيت"],
    "bghiit":   ["بغيت"],
    "khoya":    ["خويا"],
    "lalla":    ["لالة"],
    "safi":     ["صافي"],
    "zwina":    ["زوينة"],
    "zwin":     ["زوين"],
    "machi":    ["ماشي"],
    "haja":     ["حاجة"],
    "hadchi":   ["هادشي"],
    "hadi":     ["هادي"],
    "hada":     ["هادا"],
    "chno":     ["شنو"],
    "chnou":    ["شنو"],
    "chkoun":   ["شكون"],
    "fin":      ["فين"],
    "wla":      ["ولا"],
    "mashi":    ["ماشي"],
    "mazal":    ["مازال"],
    "zid":      ["زيد"],
    "aji":      ["أجي"],
    "sir":      ["سير"],
    "dkhel":    ["دخل"],
    "khrej":    ["خرج"],
}


# ---------------------------------------------------------------------------
# Tier 1: DODa direct lookup
# ---------------------------------------------------------------------------

def _doda_lookup(token: str) -> list[str]:
    """Return Arabic forms for a Darija Arabizi token, best-first.
    Checks built-in overrides first, then DODa database."""
    key = token.lower()
    overrides = _DARIJA_OVERRIDES.get(key, [])

    rows = _doda().execute(
        "SELECT arabic FROM darija WHERE arabizi = ? ORDER BY rowid",
        (key,)
    ).fetchall()
    # Deduplicate while preserving order
    seen: set[str] = set(overrides)
    result = list(overrides)
    for row in rows:
        ar = row["arabic"]
        if ar not in seen:
            seen.add(ar)
            result.append(ar)
    return result


# ---------------------------------------------------------------------------
# Tier 2: Generative transliteration
# ---------------------------------------------------------------------------

def _generate_candidates(token: str) -> list[str]:
    """
    Walk the token consuming the longest matching key at each position,
    and enumerate Arabic combinations up to MAX_CANDIDATES.
    """
    MAX_CANDIDATES = 200   # hard cap — prevents blowup on long tokens
    token_lower = token.lower()
    results: set[str] = set()

    def recurse(pos: int, current: str) -> None:
        if len(results) >= MAX_CANDIDATES:
            return
        if pos == len(token_lower):
            results.add(current)
            return
        matched = False
        for key in _SORTED_KEYS:
            if token_lower[pos:pos + len(key)] == key:
                matched = True
                for ar_letter in _EXPANDED[key]:
                    if len(results) >= MAX_CANDIDATES:
                        return
                    recurse(pos + len(key), current + ar_letter)
        if not matched:
            recurse(pos + 1, current)

    recurse(0, "")
    return list(results)


def _freq_score(word: str) -> int:
    """Return frequency score (0 if not in DB)."""
    row = _freq().execute(
        "SELECT frequency FROM frequencies WHERE word = ?", (word,)
    ).fetchone()
    return row["frequency"] if row else 0


def _generative_lookup(token: str) -> list[str]:
    """
    Generate all candidate Arabic strings and rank: known words (by freq) first,
    then unknown words (zero-freq, ordered by how primary their letter mappings are).
    Returns the full ranked list; caller applies its own limit.
    """
    candidates = _generate_candidates(token)
    # Also try with ال prefix stripped (handles 'alsalam' → السلام)
    if token.lower().startswith("al") and len(token) > 3:
        stem_candidates = _generate_candidates(token[2:])
        candidates += ["ال" + c for c in stem_candidates]

    scored = [(c, _freq_score(c)) for c in candidates]
    # Partition: known words sorted by freq descending, then unknowns
    known = sorted([(c, f) for c, f in scored if f > 0], key=lambda x: x[1], reverse=True)
    unknown = [(c, 0) for c, f in scored if f == 0]

    # Deduplicate while preserving order
    seen: set[str] = set()
    result = []
    for ar, _ in known + unknown:
        if ar not in seen:
            seen.add(ar)
            result.append(ar)
    return result


# ---------------------------------------------------------------------------
# Tier 3: Learned preferences
# ---------------------------------------------------------------------------

def _learned_choice(token: str, learned_db: sqlite3.Connection | None) -> str | None:
    """Return the user's last chosen Arabic for this token, or None."""
    if learned_db is None:
        return None
    row = learned_db.execute(
        "SELECT chosen FROM choices WHERE input = ? ORDER BY count DESC, last_used DESC LIMIT 1",
        (token.lower(),)
    ).fetchone()
    return row["chosen"] if row else None


def record_choice(token: str, chosen: str, learned_db: sqlite3.Connection) -> None:
    """Persist a user's word choice."""
    now = int(time.time())
    learned_db.execute("""
        INSERT INTO choices(input, chosen, count, last_used)
        VALUES(?, ?, 1, ?)
        ON CONFLICT(input, chosen) DO UPDATE
          SET count = count + 1,
              last_used = excluded.last_used
    """, (token.lower(), chosen, now))
    learned_db.commit()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def suggest(
    token: str,
    learned_db: sqlite3.Connection | None = None,
    max_results: int = 10,
) -> list[str]:
    """
    Return a ranked list of Arabic suggestions for `token`.

    The caller prepends the raw Latin token as item 0 (the "keep as Latin"
    option). This function returns only Arabic candidates.

    Special cases:
    - Pure number → [Arabic-Indic numeral]  (no Arabic letter)
    - URL / empty → []
    """
    if not token:
        return []

    token = token.strip()

    # Pure number (standalone)
    if re.match(r"^\d+$", token):
        return [token.translate(_ARABIC_INDIC)]

    # URL or other bypass
    if _BYPASS_RE.match(token):
        return []

    # Tier 3: learned preference
    learned = _learned_choice(token, learned_db)

    # Tier 1: DODa
    doda = _doda_lookup(token)

    # Tier 2: generative (full ranked list; we limit after merging)
    generative = _generative_lookup(token)

    # Merge: learned → doda → generative, deduplicated
    seen: set[str] = set()
    merged: list[str] = []

    def add(ar: str) -> None:
        if ar and ar not in seen:
            seen.add(ar)
            merged.append(ar)

    if learned:
        add(learned)
    for ar in doda:
        add(ar)
    for ar in generative:
        add(ar)

    return merged[:max_results]


def suggest_with_learned_first(
    token: str,
    learned_db: sqlite3.Connection | None = None,
    max_results: int = 10,
) -> tuple[list[str], int]:
    """
    Like suggest(), but also returns the index of the default-highlighted item.
    0 = first Arabic item (top of list from caller's perspective is Latin at index -1).
    Returns (candidates, default_idx) where default_idx is 0-based into candidates.
    """
    candidates = suggest(token, learned_db, max_results)
    learned = _learned_choice(token, learned_db)
    if learned and candidates and candidates[0] == learned:
        default_idx = 0
    else:
        default_idx = 0  # top Arabic candidate
    return candidates, default_idx
