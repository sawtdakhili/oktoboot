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
    result = suggest("3")
    assert result == ["٣"], f"expected ['٣'] for standalone '3', got {result}"

def test_standalone_number_4():
    result = suggest("4")
    assert result == ["٤"]

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
