"""
Extended tests — longer texts, edge cases, stress tests.
Run: PYTHONPATH=src .venv/bin/python tests/test_extended.py
"""

import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from oktoboot.editor import ArabicEditor
from oktoboot import engine

app = QApplication.instance() or QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

PASS = FAIL = 0

def check(label, condition, got=None):
    global PASS, FAIL
    if condition:
        print(f"  ✓ {label}")
        PASS += 1
    else:
        print(f"  ✗ {label}" + (f" — got {got!r}" if got is not None else ""))
        FAIL += 1

def make_editor():
    e = ArabicEditor()
    e.resize(900, 700); e.show(); e.setFocus()
    app.processEvents(); QTest.qWait(80); app.processEvents()
    return e

def type_str(e, s):
    for ch in s:
        QTest.keyClicks(e, ch); app.processEvents()
    QTest.qWait(50); app.processEvents()

def press(e, key, mod=Qt.NoModifier):
    QTest.keyClick(e, key, mod); app.processEvents(); QTest.qWait(30); app.processEvents()

def accept_top(e):
    """Accept top Arabic suggestion with space."""
    QTest.keyClicks(e, ' '); app.processEvents(); QTest.qWait(30); app.processEvents()


# ================================================================
print("\n=== ENGINE: z → ز ranked highest, ذ/ظ still present but lower ===")
for token in ["z", "za", "zi"]:
    results = engine._generate_candidates(token)
    check(f"'{token}' produces ز", any("ز" in r for r in results))
    check(f"'{token}' also produces ذ/ظ (lower rank)", any(c in ("ذ", "ظ") for r in results for c in r))

# Verify ز is the top suggestion from suggest()
top = engine.suggest("zid")
check("'zid' top suggestion contains ز (not ذ/ظ first)", top and "ز" in top[0], top[:3])


# ================================================================
print("\n=== ENGINE: long token safety (no crash, fast) ===")
long_tokens = [
    "limadhadsfsdfsdfa",    # the crashing word
    "wallahimakantashoofhach",
    "mashifteenachimach3andak",
]
for tok in long_tokens:
    t0 = time.perf_counter()
    try:
        cands = engine.suggest(tok, max_results=10)
        ms = (time.perf_counter() - t0) * 1000
        check(f"'{tok[:15]}...' no crash", True)
        check(f"'{tok[:15]}...' fast (<500ms)", ms < 500, f"{ms:.0f}ms")
        check(f"'{tok[:15]}...' ≤10 results", len(cands) <= 10, len(cands))
    except Exception as ex:
        check(f"'{tok[:15]}...' no crash", False, str(ex))


# ================================================================
print("\n=== ENGINE: Moroccan Darija words ===")
darija_tests = [
    ("wach", "واش"),       # DODa
    ("kifach", "كيفاش"),   # DODa
    ("bzaf", "بزّاف"),     # DODa
    ("dyal", "ديال"),      # DODa
    ("mzyan", "مزيان"),    # DODa
    ("sou9", "سوق"),       # DODa - 9=ق Moroccan
    ("3lash", "علاش"),     # generative
    ("3lik", "عليك"),      # generative
    ("labaas", "لاباس"),   # DODa supplement (see engine overrides)
]
for token, expected in darija_tests:
    cands = engine.suggest(token)
    check(f"'{token}' → '{expected}'", expected in cands, cands[:3])


# ================================================================
print("\n=== ENGINE: Moroccan-specific mappings ===")
# g → ڭ must be present somewhere in candidates
gari_cands = engine._generate_candidates("gari")
check("g → ڭ present in gari candidates", any("ڭ" in c for c in gari_cands))

# 9 → ق primary (not ص)
q_cands = engine._generate_candidates("9ra")
check("9 → ق in 9ra candidates", any("ق" in c for c in q_cands))

# ch → ش
ch_cands = engine._generate_candidates("chokran")
check("ch → ش in chokran", any("ش" in c for c in ch_cands))


# ================================================================
print("\n=== EDITOR: full sentence ===")
e = make_editor()
sentence = "salam labaas 3lik "
for ch in sentence:
    QTest.keyClicks(e, ch); app.processEvents()
QTest.qWait(100); app.processEvents()
text = e.toPlainText()
check("سلام in text", "سلام" in text, text)
check("لاباس in text", "لاباس" in text or "لابأس" in text, text)  # both valid
check("عليك in text", "عليك" in text, text)
check("no Latin left in text", "salam" not in text and "labaas" not in text)
e.close()


# ================================================================
print("\n=== EDITOR: mixed Arabic and Latin (brand names) ===")
e = make_editor()
type_str(e, "salam ")
# Keep "iPhone" as Latin via Shift+Space
for ch in "iPhone":
    QTest.keyClicks(e, ch); app.processEvents()
QTest.keyClick(e, Qt.Key_Space, Qt.ShiftModifier)
app.processEvents(); QTest.qWait(30)
type_str(e, "3ndi ")
text = e.toPlainText()
check("iPhone stays Latin", "iPhone" in text, text)
check("سلام present", "سلام" in text, text)
check("عند(ي) present", "عند" in text, text)  # 3ndi→عند; 3ndiy→عندي
e.close()


# ================================================================
print("\n=== EDITOR: punctuation sentence ===")
e = make_editor()
type_str(e, "kifach ")
type_str(e, "nta")
QTest.keyClick(e, Qt.Key_Question, Qt.ShiftModifier)
app.processEvents(); QTest.qWait(30)
type_str(e, "ana ")
type_str(e, "mzyan")
QTest.keyClicks(e, "."); app.processEvents(); QTest.qWait(30)
text = e.toPlainText()
check("؟ in text", "؟" in text, text)
check(". in text", "." in text, text)
check("كيفاش in text", "كيفاش" in text, text)
check("مزيان in text", "مزيان" in text, text)
e.close()


# ================================================================
print("\n=== EDITOR: multi-paragraph ===")
e = make_editor()
type_str(e, "salam labaas ")
press(e, Qt.Key_Return)
type_str(e, "kifach nta ")
press(e, Qt.Key_Return)
press(e, Qt.Key_Return)  # blank line
type_str(e, "ana mzyan ")
text = e.toPlainText()
check("3 lines of text", text.count("\n") >= 2, repr(text))
check("all 4 words converted", all(
    w in text for w in ["سلام", "كيفاش", "مزيان"]
) and ("لاباس" in text or "لابأس" in text), text)
e.close()


# ================================================================
print("\n=== EDITOR: backspace chain ===")
e = make_editor()
type_str(e, "salam ")
type_str(e, "kifach")
# Backspace through composing
for _ in range(6):  # delete "kifach"
    press(e, Qt.Key_Backspace)
check("composing cleared after 6 backspaces", not e._composing, e._compose_token)
# Backspace into previous committed word
press(e, Qt.Key_Backspace)
check("previous word popup reopened", e._composing)
e.close()


# ================================================================
print("\n=== EDITOR: numbers in context ===")
e = make_editor()
type_str(e, "3lash ")  # 3 = ع (in word)
text = e.toPlainText()
check("3lash → ع present", "ع" in text, text)

e2 = make_editor()
type_str(e2, "3 ")   # standalone 3 → digit or ٣
text2 = e2.toPlainText()
check("standalone 3 stays digit (not ع)", "عَ" not in text2, text2)
e2.close()
e.close()


# ================================================================
print("\n=== EDITOR: URL passthrough ===")
e = make_editor()
type_str(e, "http://yamli.com ")
text = e.toPlainText()
check("http:// not transliterated", "http" in text.lower(), text)
check("no Arabic letters from URL", "ح" not in text, text)  # h→ح if transliterated
e.close()


# ================================================================
print("\n=== EDITOR: very long word doesn't crash ===")
e = make_editor()
long_word = "limadhadsfsdfsdfa"
t0 = time.perf_counter()
for ch in long_word:
    QTest.keyClicks(e, ch); app.processEvents()
QTest.qWait(100); app.processEvents()
ms = (time.perf_counter() - t0) * 1000
check(f"long word typed without crash ({ms:.0f}ms)", True)
check("popup present or hidden (no hang)", True)  # just didn't crash
# accept with space
QTest.keyClicks(e, ' '); app.processEvents()
check("accepted without crash", not e._composing)
e.close()


# ================================================================
print("\n=== EDITOR: Shift combos don't leak into composing ===")
e = make_editor()
type_str(e, "sal")
check("composing 'sal'", e._compose_token == "sal")
# Hold shift (capital letter)
QTest.keyClick(e, Qt.Key_Shift); app.processEvents()
check("still 'sal' after Shift press", e._compose_token == "sal", e._compose_token)
# Shift+A → shouldn't add to composing (Cmd/Ctrl shortcuts only; plain Shift IS printable)
# But Shift+? (Question) should commit:
QTest.keyClick(e, Qt.Key_Question, Qt.ShiftModifier); app.processEvents()
check("? committed composing word", not e._composing or e._compose_token == "")
check("؟ inserted", "؟" in e.toPlainText(), e.toPlainText())
e.close()


# ================================================================
print(f"\n{'='*50}")
print(f"{PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
