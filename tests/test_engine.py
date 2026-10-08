"""Unit tests for the transliteration engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oktoboot.engine import suggest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def top(token: str, n: int = 3) -> list[str]:
    return suggest(token)[:n]


def assert_top(token: str, expected: str, label: str = "") -> None:
    results = suggest(token)
    label = label or f"suggest({token!r})"
    assert results, f"{label}: got empty list"
    assert expected in results[:3], (
        f"{label}: expected {expected!r} in top 3, got {results[:3]!r}"
    )


def assert_first(token: str, expected: str) -> None:
    results = suggest(token)
    assert results, f"suggest({token!r}): got empty list"
    assert results[0] == expected, (
        f"suggest({token!r}): expected {expected!r} first, got {results[0]!r}"
    )


# ---------------------------------------------------------------------------
# MSA basics
# ---------------------------------------------------------------------------

def test_salam():
    assert_top("salam", "سلام")

def test_salam_capital():
    # Case-insensitive — same result as lowercase
    assert top("Salam") == top("salam")

def test_min():
    assert_top("min", "من")

def test_fi():
    assert_top("fi", "في")

# ---------------------------------------------------------------------------
# Moroccan Darija via DODa (Tier 1)
# ---------------------------------------------------------------------------

def test_kifach_doda():
    assert_first("kifach", "كيفاش")

def test_bzaf_doda():
    assert_first("bzaf", "بزّاف")

def test_dyal_doda():
    assert_first("dyal", "ديال")

def test_mzyan_doda():
    assert_first("mzyan", "مزيان")

def test_sou9_doda():
    assert_first("sou9", "سوق")

# ---------------------------------------------------------------------------
# Moroccan-specific mappings
# ---------------------------------------------------------------------------

def test_3lash_3_is_ayn():
    results = suggest("3lash")
    assert results, "suggest('3lash') returned empty"
    # علاش should appear — 3 → ع
    has_ayn = any("ع" in r for r in results)
    assert has_ayn, f"expected ع (ayn) in candidates for '3lash', got {results[:5]}"

def test_9_is_qaf():
    results = suggest("9ra")
    assert results
    # 9 → ق (Moroccan)
    has_qaf = any("ق" in r for r in results)
    assert has_qaf, f"expected ق in candidates for '9ra', got {results[:5]}"

def test_ch_is_shin():
    results = suggest("chokran")
    assert results
    has_shin = any("ش" in r for r in results)
    assert has_shin, f"expected ش in candidates for 'chokran', got {results[:5]}"

def test_g_has_gaf():
    # g → ڭ must be generated. ڭاري (Moroccan "taxi") has MSA freq=0 so it
    # sits in the "more choices" tail, but must be findable. After the user
    # picks it once, learned.db promotes it to the top permanently.
    from oktoboot.engine import _generative_lookup
    all_candidates = _generative_lookup("gari")
    has_gaf = any("ڭ" in c for c in all_candidates)
    assert has_gaf, f"ڭ not in any candidate for 'gari': {all_candidates}"
    # ڭاري specifically
    assert "ڭاري" in all_candidates, f"ڭاري not generated for 'gari': {all_candidates}"

def test_kh_is_kha():
    results = suggest("khobar")
    assert results
    has_kha = any("خ" in r for r in results)
    assert has_kha, f"expected خ in candidates for 'khobar', got {results[:5]}"

# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def test_standalone_number_arabic_indic():
    # Arabic-Indic numeral ranks first; the plain digit stays reachable
    # as a fallback (folded into the ranked list, not a separate slot).
    result = suggest("3")
    assert result == ["٣", "3"], f"expected ['٣', '3'] for standalone '3', got {result}"

def test_standalone_number_4():
    result = suggest("4")
    assert result == ["٤", "4"]

def test_number_in_word():
    # 3lash — 3 treated as letter, not digit
    results = suggest("3lash")
    assert results
    assert "٣" not in results[0], f"digit conversion should not apply in '3lash'"

# ---------------------------------------------------------------------------
# URLs (bypass)
# ---------------------------------------------------------------------------

def test_url_bypass():
    assert suggest("http://example.com") == []

def test_www_bypass():
    assert suggest("www.google.com") == []

# ---------------------------------------------------------------------------
# al- prefix
# ---------------------------------------------------------------------------

def test_al_prefix():
    results = suggest("alsalam")
    assert results
    has_al = any("ال" in r for r in results)
    assert has_al, f"expected ال prefix in candidates for 'alsalam', got {results[:5]}"

# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty():
    assert suggest("") == []

def test_single_s():
    results = suggest("s")
    assert results
    # س should appear (s → س primary)
    assert "س" in results or any("س" in r for r in results[:3])


def test_latin_fallback_ranked_not_pinned():
    """The raw Latin token is folded into the same ranked list as Arabic
    candidates: a low-priority fallback by default, promoted to the top
    via the same learned-choice mechanism as any other pick — no special
    'keep as Latin' sentinel or fixed slot."""
    import sqlite3
    from oktoboot.engine import suggest, record_choice

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute(
        "CREATE TABLE choices (input TEXT NOT NULL, chosen TEXT NOT NULL, "
        "count INTEGER DEFAULT 1, last_used INTEGER, PRIMARY KEY(input, chosen))"
    )
    db.commit()

    before = suggest("iphone", db)
    assert before, "expected at least the Latin fallback"
    assert before[0] != "iphone", f"Latin shouldn't rank first before any learning, got {before}"
    assert "iphone" in before, f"Latin should still be reachable as a fallback, got {before}"

    record_choice("iphone", "iphone", db)
    after = suggest("iphone", db)
    assert after[0] == "iphone", f"learned 'keep as Latin' should rank first, got {after}"
    assert after.count("iphone") == 1, f"should not duplicate, got {after}"


def test_bug_regressions():
    """Regressions for bugs found by comparing against Yamli."""
    # Bad DODa entry: bgha→با was ranked above بغا
    assert_first("bgha", "بغا")
    # Egyptian word لسه was frequency-promoted above Moroccan لاش
    assert_first("lach", "لاش")
    # Vowel absorption: "ra"→ر and "na"→ن swallowed both alifs in رانا
    assert_first("rana", "رانا")
    # Expansion absorbed final 'a': "ta"→ت gave حت instead of حتى
    assert_first("7ta", "حتى")
    # DODa had hna→حنا (we) but users almost always mean هنا (here)
    assert_first("hna", "هنا")
    # Frequency corpus promoted ماء over ما
    assert_first("ma", "ما")
    # DODa returned علا before على
    assert_first("3la", "على")
    # Final "an" is tanwin: شكراً, then شكرا, then the literal شكران
    # (Saad, 2026-10-08 — replaced the July "شكران first" override).
    assert suggest("chokran")[:3] == ["شكراً", "شكرا", "شكران"], suggest("chokran")[:3]
    # Expansion absorbed final 'a': عليه instead of عليها
    assert_first("3liha", "عليها")
    # Generative produced space-separated "و لكن"; fixed to ولكن
    assert_first("walakin", "ولكن")
    # Bad DODa entry: fi→ف (letter) ranked above في (preposition)
    assert_first("fi", "في")
    # Moroccan function words that must beat corpus noise
    assert_first("fach", "فاش")
    assert_first("bach", "باش")
    assert_first("3lach", "علاش")
    # Final long ā written as alef maqsura (ى) was unreachable entirely —
    # no key in MAPPING produced ى, so no word ending in it (موسى، عيسى،
    # متى، وتولى...) was ever a candidate at any rank. _FINAL_EXTRA fixed
    # this generatively (no dictionary/override needed).
    assert_first("moussa", "موسى")
    assert_first("3issa", "عيسى")
    assert_first("mata", "متى")
    # "watawala" was the case that surfaced the bug: fixing reachability
    # alone doesn't guarantee #1 (a same-length alternate reading, وطوال,
    # is more "regular" and ranks first) — but the old len(token)-1 demotion
    # rule buried وتولى outside the top 3 entirely under 8-glyph junk like
    # واتاوالا. Top-3 is the meaningful guarantee here, not first place.
    assert_top("watawala", "وتولى")


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    if failed:
        sys.exit(1)
