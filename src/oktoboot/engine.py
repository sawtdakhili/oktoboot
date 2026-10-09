"""
Transliteration engine — three tiers:

  Tier 1: DODa direct lookup  → exact Darija words
  Tier 2: Generative + frequency filter  → MSA and novel words
  Tier 3: Learned preferences  → user's own persistent choices

Result: ranked list of candidates, best-first. The raw Latin token itself is
one of the candidates (folded into the same ranking, not a fixed slot) —
see suggest()'s docstring.
"""

from __future__ import annotations

import math
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    """`data/` next to the source tree when run from source; inside the
    bundle when frozen by PyInstaller (which unpacks to sys._MEIPASS)."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "data"
    return Path(__file__).parent.parent.parent / "data"


DATA_DIR = _data_dir()
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
    "x":  ["ش", "كس"],          # Maghreb texting: wax → واش, xhal → شحال
    "y":  ["ي"],
    "z":  ["ز", "ذ", "ظ"],   # ز primary, ذ/ظ lower-ranked alternatives

    # vowels / semi-vowels
    "a":  ["ا", "أ"],
    "e":  ["ي", "ا", "ه"],         # ة only word-final, via _FINAL_EXTRA
    "i":  ["ي", "ا"],
    "o":  ["و", "أ"],
    "u":  ["و", "أ"],

    # digraph vowels
    "ou": ["و"],
    "oo": ["و"],
    "ee": ["ي"],
    "ai": ["ي"],
    "ei": ["ي"],
    "aa": ["ا", "عا"],             # word-initial: آ first, see _INITIAL_LETTERS
    "allah": ["الله"],            # inchallah → إنشالله, not ...الاه
    "llah": ["لله"],              # 7amdollah → حمدلله
    "2aa": ["آ"],                 # qor2aan → قرآن

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

SHADDA = "ّ"
TANWIN_FATH = "ً"  # fathatan: chokran → شكراً

# Doubled Latin consonant ("mm", "ss", "ll") → one Arabic letter with
# shadda. The literal double (م+م) stays reachable through two single keys.
# Lookups strip the shadda; see _generative_lookup for display order.
_DOUBLABLE = "bcdfghjklmnpqrstvwyz"


@dataclass(frozen=True)
class _Key:
    letters: list[str]
    absorbed: str = ""        # vowel swallowed by a consonant+vowel key ("ka" → ك)
    vowel: bool = False       # key is itself a vowel ("a", "ou", ...)
    base: str = ""            # the MAPPING key it comes from ("z" for "zz", "za")


_KEYS: dict[str, _Key] = {
    k: _Key(letters, vowel=k[0] in _VOWEL_LETTERS, base=k) for k, letters in MAPPING.items()
}
for _c in _DOUBLABLE:
    _KEYS.setdefault(_c * 2, _Key([L + SHADDA for L in MAPPING[_c]], base=_c))
for _key, _info in list(_KEYS.items()):
    if not _info.vowel:
        for _v in _VOWELS:
            _KEYS.setdefault(_key + _v, _Key(_info.letters, absorbed=_v, base=_info.base))

# Letters a key almost never means in North African Arabizi: kept in the
# list, but well below the usual ones. z is ز; ذ/ظ are written d or dh
# (Saad, 2026-10-09: ذنب was showing right under زينب).
_RARE_LETTER_COST: dict[tuple[str, str], float] = {
    ("z", "ذ"): 3.0,
    ("z", "ظ"): 3.0,
}

_SORTED_KEYS = sorted(_KEYS, key=lambda k: (-len(k), k))

# Word-final long ā is very often written as alef maqsura (ى) or ta marbuta
# (ة): "watawala"→وتولى, "moustafa"→مصطفى, "zwina"→زوينة, "3la"→على. Neither
# letter can appear mid-word, so they're offered only when the matched key
# consumes the end of the token (see _generate_candidates). CV keys like
# "la" don't need entries: the ل+ى path is reachable via "l" then final "a".
_FINAL_EXTRA: dict[str, list[str]] = {
    "a":  ["ى", "ة"],
    "aa": ["ى"],
}

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
    "nta":      ["نتا"],
    "nti":      ["نتي"],
    "hna":      ["هنا", "حنا"],   # "here" is far more common than "we"
    "ntoma":    ["نتوما"],
    "ntuma":    ["نتوما"],
    "ntouma":   ["نتوما"],
    "homa":     ["هوما"],
    "daba":     ["دابا"],
    "gadi":     ["غادي"],
    "kayn":     ["كاين"],
    "makaynch": ["ماكاينش"],
    "makainch": ["ماكاينش"],
    "bghit":    ["بغيت"],
    "bghiit":   ["بغيت"],
    "bgha":     ["بغا"],          # DODa has bad entry "با" at rowid 1
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
    # Function words: corpus or bad DODa entries promote wrong forms
    "fi":       ["في"],
    "ma":       ["ما"],
    "3la":      ["على"],
    "lach":     ["لاش"],
    "fach":     ["فاش"],
    "3lach":    ["علاش"],
    "bach":     ["باش"],
    "7ta":      ["حتى"],
    "walakin":  ["ولكن"],
    "walkin":   ["ولكن"],
    "3liha":    ["عليها"],
    "rana":     ["رانا", "رنا"],  # Moroccan progressive "rah-na"; also name رنا
    # Bad DODa entries: a translation instead of a spelling (nhar→يوم),
    # the wrong word (had→هادا is "hada"), the article added (drari→الدراري)
    "nhar":     ["نهار"],
    "had":      ["هاد"],
    "drari":    ["دراري"],
    # "chh" reads as c + doubled h (سهّ...) and the corpus favours سهل
    "chhal":    ["شحال"],
    # Saad's order (2026-10-08): tanwin, then without it, then the literal ن
    "chokran":  ["شكراً", "شكرا", "شكران"],
    # Darija adjective; the corpus's MSA نادماً would otherwise win (tanwin rule)
    "nadman":   ["ندمان"],
    "taxi":     ["طاكسي", "تاكسي"],   # x = ش would give تشي
    # DODa lists امن first; typed with a leading "aa" it's almost always amen
    "aamin":    ["آمين", "آمن"],
    # Typed with its hamza, the phrase is meant in full
    "insha2allah":  ["إن شاء الله", "إنشاء الله"],
    "incha2allah":  ["إن شاء الله", "إنشاء الله"],
}

# Common Moroccan first names (several Latin spellings each). Letter rules
# can't get names right — ع, ص, ة, ى and long vowels are unpredictable — so
# they're listed. Only names the engine got wrong on 2026-10-09 are here.
_NAMES: dict[str, str] = {
    "مصطفى": "moustafa mustapha mostafa mustafa moustapha mostapha",
    "حمزة": "hamza",
    "فاطمة": "fatima fatma",
    "فتيحة": "fatiha",
    "زينب": "zineb zaynab zeinab",
    "رشيد": "rachid rashid",
    "عمر": "omar omer",
    "عثمان": "othmane otmane othman otman",
    "سلمى": "salma",
    "عائشة": "aicha aisha",
    "عبد الله": "abdellah abdallah abdelah abdullah abdollah",
    "عبد الرحيم": "abderrahim abdelrahim abderahim",
    "عبد القادر": "abdelkader abdelkadar abdelqader",
    "عبد الرحمن": "abderrahman abderrahmane abdelrahman",
    "عبد العزيز": "abdelaziz",
    "عبد الكريم": "abdelkrim abdelkarim",
    "عبد اللطيف": "abdellatif abdelatif",
    "عبد الحق": "abdelhak abdelhaq",
    "عبد الصمد": "abdessamad abdesamad",
    "سعيد": "said saeed",
    "إدريس": "driss idriss idris",
    "سفيان": "soufiane sofiane soufian sofian",
    "أنس": "anas",
    "إلياس": "ilyas ilias elias",
    "زكرياء": "zakaria zakariae zakariya",
    "أحمد": "ahmed ahmad",
    "علي": "ali",
    "آدم": "adam",
    "إسماعيل": "ismail smail",
    "رضا": "reda rida",
    "وليد": "walid",
    "طارق": "tarik tariq tarek",
    "سميرة": "samira",
    "نعيمة": "naima",
    "مليكة": "malika",
    "هدى": "houda hoda",
    "أسماء": "asmae asma asmaa",
    "لبنى": "loubna lobna",
    "كنزة": "kenza",
    "لمياء": "lamia lamya",
    "نادية": "nadia",
    "سعاد": "souad",
    "عبدو": "abdo",
    "عزيز": "aziz",
    "إبراهيم": "brahim ibrahim",
    "فاطنة": "fatna",
    "يوسف": "youssef yousef youssouf",
    "ياسين": "yassine yasin yassin",
    "مهدي": "mehdi mahdi",
    "خديجة": "khadija khadidja",
    "كريم": "karim",
    "هشام": "hicham hisham",
    "أيوب": "ayoub ayyoub",
    "إيمان": "imane iman",
    "هاجر": "hajar",
    "نبيل": "nabil",
    "مريم": "meryem maryam meriem",
    "خالد": "khalid khaled",
    "محمد": "mohamed mohammed mohamad mhamed",
    "أمين": "amine",
    "يونس": "younes younous",
    "جمال": "jamal",
    "حميد": "hamid",
    "سارة": "sara sarah",
    "نور": "nour",
    "حسن": "hassan",
    "حسين": "hussein houssine",
}
for _name, _spellings in _NAMES.items():
    for _latin in _spellings.split():
        _DARIJA_OVERRIDES.setdefault(_latin, [_name])


# ---------------------------------------------------------------------------
# Tier 1: DODa direct lookup
# ---------------------------------------------------------------------------

def _doda_lookup(token: str) -> list[str]:
    """Return Arabic forms for a Darija Arabizi token, best-first.
    Checks built-in overrides first, then DODa database."""
    key = token.lower()
    overrides = _DARIJA_OVERRIDES.get(key, [])
    if not overrides and "x" in key:
        # x is texting shorthand for ch (xhal = chhal): same entries.
        alias = key.replace("x", "ch")
        if alias in _DARIJA_OVERRIDES or _doda().execute(
                "SELECT 1 FROM darija WHERE arabizi = ? LIMIT 1", (alias,)).fetchone():
            return _doda_lookup(alias)

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
# Every candidate carries a cost: how far it strays from the most typical
# reading of each Latin key. Costs only ORDER candidates, never remove one —
# an unusual spelling stays reachable further down the list.

_KEY_COST = 0.5           # per key consumed: a digraph (kh→خ) beats a split (k+h→كه)
_ALT_COST = 1.0           # per step down a key's letter list (s→ص is one step past س)
# A short vowel either disappears into the consonant before it ("ka"→ك) or
# is written as its own letter ("k"+"a"→كا, which also pays one more
# _KEY_COST). Darija Arabizi usually writes a, i, o, u as letters, and
# usually drops e (a schwa: "khdem"→خدم).
_ABSORB_COST = {"a": 1.2, "e": 0.0, "i": 1.0, "o": 1.0, "u": 1.0}
_WRITE_COST = {"a": 0.0, "e": 1.0, "i": 0.0, "o": 0.0, "u": 0.0}
_FINAL_ABSORB_COST = 2.0  # a word-final vowel is almost always written
_FINAL_EXTRA_COST = 0.8   # ى / ة for a word-final ā
# أ/إ/آ in the middle of a word from a plain vowel key (not a typed "2"):
# real words (سأل، رأس) still get through on their frequency; made-up ones
# (كأنبغيك) sink below the plain-alef reading.
_MEDIAL_HAMZA_COST = 3.0
_HAMZA_SEATS = set("أإآ")
_BEAM = 300               # partial spellings kept per position
# Reading a final "an" as tanwin (شكراً) instead of ا+ن. High enough that
# names keep their ن (رمضان, سلمان); very common tanwin words still win on
# frequency (شكراً, جداً, أيضاً).
_TANWIN_COST = 2.0

# Darija verb prefixes, only at the very start of a word: the prefix's
# vowel is short and never written (kanbghi→كنبغي, kaykhdem→كيخدم,
# katchouf→كتشوف). One key each, so they beat k+a+n spelled out.
_PREFIX_KEYS: dict[str, list[str]] = {
    "kan": ["كن"],
    "kay": ["كي"],
    "kat": ["كت"],
}

# Keys that read differently at the very start of a word: a long ā there
# is written آ (aamin→آمين, aakhir→آخر); mid-word "aa" stays ا.
_INITIAL_LETTERS: dict[str, list[str]] = {
    "aa": ["آ", "عا"],
    # A word never starts with a vowel letter ي/و standing for i/o: it's an
    # alef with or without hamza (ism→اسم, inchallah→إنشالله, omar→أمر).
    "i": ["إ", "ا", "ي"],
    "e": ["ا", "إ", "ي"],
    "o": ["أ", "ا", "و"],
    "u": ["أ", "ا", "و"],
}

# Frequency vs. typicality: score = log10(freq + 1) - _COST_WEIGHT * cost.
# The weights above and this one were tuned together on
# tests/test_darija_words.py (2026-10-08) while keeping test_engine.py green;
# re-run both after changing any of them.
_COST_WEIGHT = 0.8


def _hamza_letters(t: str, pos: int, end: int, info: _Key) -> list[str]:
    """
    A typed "2" (hamza), its seat chosen from the vowels around it, as
    written Arabic does: next to i → ئ (ra2is → رئيس), next to o/u → ؤ
    (su2al → سؤال, mo2min → مؤمن), at the start → أ/إ, at the end after
    a consonant or ā → ء (sma2 → سماء), otherwise أ. The other seats
    follow in their usual order.
    """
    prev = t[pos - 1] if pos > 0 else ""
    nxt = info.absorbed or (t[end] if end < len(t) else "")
    if pos == 0:
        seat = "إ" if nxt in ("i", "e") else "أ"
    elif not nxt:
        seat = "ئ" if prev == "i" else "ؤ" if prev in ("o", "u") else "ء"
    elif "i" in (prev, nxt):
        seat = "ئ"
    elif prev in ("o", "u") or nxt in ("o", "u"):
        seat = "ؤ"
    else:
        seat = "أ"
    return [seat] + [L for L in MAPPING["2"] if L != seat]


def _generate_candidates(token: str) -> dict[str, float]:
    """
    All spellings of `token` the key table allows, each with its cost.
    Beam search, left to right: at each position every matching key and
    every letter option extends the cheapest partial spellings. Fully
    deterministic — ties break on the spelling itself.
    """
    t = token.lower()
    n = len(t)
    states: list[dict[str, float]] = [dict() for _ in range(n + 1)]
    states[0][""] = 0.0

    def push(pos: int, out: str, cost: float) -> None:
        if cost < states[pos].get(out, float("inf")):
            states[pos][out] = cost

    for pos in range(n):
        if not states[pos]:
            continue
        best = sorted(states[pos].items(), key=lambda x: (x[1], x[0]))[:_BEAM]
        matched = False
        if pos == 0:
            for key, letters in _PREFIX_KEYS.items():
                if t.startswith(key) and len(t) > len(key):
                    for out, cost in best:
                        push(len(key), out + letters[0], cost + _KEY_COST)
        for key in _SORTED_KEYS:
            if not t.startswith(key, pos):
                continue
            matched = True
            end = pos + len(key)
            final = end == n
            info = _KEYS[key]
            base = _KEY_COST
            if info.absorbed:
                base += _FINAL_ABSORB_COST if final else _ABSORB_COST[info.absorbed]
            if info.vowel:
                base += _WRITE_COST[key[0]]
            letters = _INITIAL_LETTERS.get(key, info.letters) if pos == 0 else info.letters
            if info.base == "2":
                letters = _hamza_letters(t, pos, end, info)
            options = [(letter, i * _ALT_COST + _RARE_LETTER_COST.get((info.base, letter.rstrip(SHADDA)), 0.0))
                       for i, letter in enumerate(letters)]
            if final:
                options += [(letter, _FINAL_EXTRA_COST) for letter in _FINAL_EXTRA.get(key, [])]
            for letter, step in options:
                c = base + step
                if pos > 0 and letter[0] in _HAMZA_SEATS and key[0] != "2":
                    c += _MEDIAL_HAMZA_COST
                for out, cost in best:
                    push(end, out + letter, cost + c)
        if not matched:  # character with no key: skip it
            for out, cost in best:
                push(pos + 1, out, cost)

    return states[n]


def _freq_score(word: str) -> int:
    """Return frequency score (0 if not in DB)."""
    row = _freq().execute(
        "SELECT frequency FROM frequencies WHERE word = ?", (word,)
    ).fetchone()
    return row["frequency"] if row else 0


def _min_expected_len(token: str) -> int:
    """
    Lower bound on how many Arabic letters a faithful transliteration of a
    vowel-final token should have: one per consonant unit, plus one for the
    final long vowel (word-final ā/ī/ū is always written — as ا/ى/ي/و —
    unlike interior short vowels, which usually aren't).

    Deliberately NOT len(token)-1: that assumed every Latin letter becomes
    an Arabic letter, which is false for any multi-syllable word — it buried
    the correct وتولى (5 letters) under letter-by-letter 8-glyph junk for
    "watawala".
    """
    t = token.lower()
    t = re.sub(r"ch|sh|gh|kh|dh|dj|th", "x", t)   # digraph = one Arabic letter
    t = re.sub(r"(.)\1+", r"\1", t)               # doubles = shadda / one long vowel
    # A trailing glide+vowel ("hya"→هي, "howa"→هو) writes the glide AS the
    # final vowel letter; don't also count it as a required consonant.
    t = re.sub(r"[wy][aeiou]$", "", t)
    consonants = len(re.sub(r"[aeiou']", "", t))
    return consonants + 1


def _generative_lookup(token: str) -> list[str]:
    """
    Rank every generated spelling, best-first: corpus frequency (log scale)
    minus how atypical the spelling is. Unknown words (frequency 0) rank by
    typicality alone. Returns the full ranked list; caller applies its own
    limit.

    Shadda spellings (from doubled letters) are looked up and ranked by
    their plain form; each is listed right after it (محمد, then محمّد).
    """
    candidates = _generate_candidates(token)
    t = token.lower()
    # Article: "al" + word (alsalam → السلام), and Darija's bare "l" before
    # a consonant (lmaghrib → المغرب, lmizan → الميزان). The ل-only spelling
    # (لمغرب) stays in the list; frequency usually prefers the full article.
    for prefix in ("al", "l"):
        rest = t[len(prefix):]
        if (t.startswith(prefix) and len(rest) >= 3
                and (prefix == "al" or rest[0] not in _VOWEL_LETTERS)):
            for c, cost in _generate_candidates(rest).items():
                out = "ال" + c
                if cost + _KEY_COST < candidates.get(out, float("inf")):
                    candidates[out] = cost + _KEY_COST

    # Final "an" is often tanwin, not a written ن: chokran → شكراً (and the
    # same word without its tanwin, شكرا), jiddan → جداً. Built from the
    # spellings of the token minus its "n" that end in ا; frequency decides
    # between them and a real final ن (zaman → زمان still wins).
    if len(token) >= 3 and token.lower().endswith("an"):
        for c, cost in _generate_candidates(token[:-1]).items():
            if c.endswith("ا"):
                for out, extra in ((c + TANWIN_FATH, _TANWIN_COST), (c, _TANWIN_COST + 0.5)):
                    if cost + extra < candidates.get(out, float("inf")):
                        candidates[out] = cost + extra

    plain_cost: dict[str, float] = {}
    shadda_form: dict[str, tuple[float, str]] = {}
    for c, cost in candidates.items():
        plain = c.replace(SHADDA, "")
        if cost < plain_cost.get(plain, float("inf")):
            plain_cost[plain] = cost
        if c != plain and (plain not in shadda_form or (cost, c) < shadda_form[plain]):
            shadda_form[plain] = (cost, c)

    # When input ends with a vowel, consonant-absorbing keys can silently drop
    # output letters (e.g. "rana"→رن instead of رانا because "ra"→ر, "na"→ن).
    # Candidates below the consonant-count floor are likely truncated: sink
    # them below everything else. Tokens shorter than 3 chars are exempt
    # ("wa"→و is legitimately one letter).
    vowel_final = token[-1].lower() in "aeiou" if token else False
    min_expected = _min_expected_len(token) if (vowel_final and len(token) >= 3) else 0

    def score(plain: str) -> float:
        s = math.log10(_freq_score(plain) + 1) - _COST_WEIGHT * plain_cost[plain]
        if len(plain) < min_expected:
            s -= 100
        return s

    ranked = sorted(plain_cost, key=lambda p: (-score(p), p))
    result: list[str] = []
    for plain in ranked:
        result.append(plain)
        if plain in shadda_form:
            result.append(shadda_form[plain][1])
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
    Return a ranked list of suggestions for `token`, best-first — the item
    at index 0 is always the intended default/highlighted choice.

    The raw Latin token itself is one of the candidates, not a separate
    fixed slot: it's folded into the same three-tier ranking as everything
    else. If the user has previously chosen (via Shift+Space) to keep this
    exact token in Latin, that's a learned choice like any other and ranks
    accordingly (usually first). Otherwise it's appended as a low-priority
    fallback so it's always reachable without crowding out real candidates.

    Special cases:
    - Pure number → [Arabic-Indic numeral, digit fallback]
    - URL / empty → []
    """
    if not token:
        return []

    token = token.strip()

    # Pure number (standalone) — Arabic-Indic numeral ranks first, the
    # plain digit is always reachable as a fallback.
    if re.match(r"^\d+$", token):
        return [token.translate(_ARABIC_INDIC), token]

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

    if token in seen:
        # Already ranked via the learned tier above (usually first).
        return merged[:max_results]

    # Not learned — Latin is always a reachable fallback. Reserve its slot
    # within max_results rather than appending past the cap (callers rely
    # on the cap as a hard limit).
    result = merged[: max(max_results - 1, 0)]
    result.append(token)
    return result
