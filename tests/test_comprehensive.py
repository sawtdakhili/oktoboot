"""
Comprehensive editor behavior tests — covers all known and suspected edge cases.
Run: PYTHONPATH=src .venv/bin/python tests/test_comprehensive.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextCursor, QKeyEvent

from oktoboot.editor import ArabicEditor

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
    e.resize(800, 600)
    e.show(); e.setFocus()
    app.processEvents(); QTest.qWait(50); app.processEvents()
    return e

def type_str(e, s):
    for ch in s:
        QTest.keyClicks(e, ch)
        app.processEvents()
    QTest.qWait(30); app.processEvents()

def press(e, key, mod=Qt.NoModifier):
    QTest.keyClick(e, key, mod)
    app.processEvents(); QTest.qWait(30); app.processEvents()


# ============================================================
print("\n=== 1. RTL alignment ===")
e = make_editor()
check("cursor starts at right edge (RTL)", e.cursorRect().x() > e.viewport().width() * 0.7)
e.close()


# ============================================================
print("\n=== 2. Basic word + space ===")
e = make_editor()
type_str(e, "salam ")
check("سلام accepted on space", "سلام" in e.toPlainText(), e.toPlainText())
check("not composing", not e._composing)
e.close()


# ============================================================
print("\n=== 3. Modifier keys don't commit composing word ===")
e = make_editor()
type_str(e, "3li")
check("composing '3li'", e._compose_token == "3li")
# Shift held (for ?)
QTest.keyClick(e, Qt.Key_Shift)
app.processEvents()
check("still composing after Shift press", e._composing and e._compose_token == "3li",
      e._compose_token)
# Cmd held
QTest.keyClick(e, Qt.Key_Meta)
app.processEvents()
check("still composing after Cmd press", e._composing and e._compose_token == "3li")
e.close()


# ============================================================
print("\n=== 4. Shift+? accepts highlighted and inserts ؟ ===")
e = make_editor()
type_str(e, "3lik")
highlighted = e._popup.current_text()
print(f"     highlighted: {highlighted!r}")
QTest.keyClick(e, Qt.Key_Question, Qt.ShiftModifier)
app.processEvents(); QTest.qWait(50)
text = e.toPlainText()
print(f"     text after Shift+?: {text!r}")
check("؟ inserted", "؟" in text, text)
check("Arabic word accepted (not '3lik')", "3lik" not in text, text)
check("highlighted item accepted", highlighted and highlighted in text)
e.close()


# ============================================================
print("\n=== 5. Other Shift combos ===")
e = make_editor()
type_str(e, "salam")
highlighted = e._popup.current_text()
# Shift+1 → ! (passthrough punctuation)
QTest.keyClick(e, Qt.Key_Exclam, Qt.ShiftModifier)
app.processEvents(); QTest.qWait(30)
text = e.toPlainText()
check("! inserted after accepting", "!" in text, text)
check("arabic word accepted with !", highlighted and highlighted in text)
e.close()


# ============================================================
print("\n=== 6. Cmd+A (select all) while composing ===")
e = make_editor()
type_str(e, "salam ")
type_str(e, "kifa")
check("composing 'kifa'", e._compose_token == "kifa")
press(e, Qt.Key_A, Qt.ControlModifier)  # Cmd+A
app.processEvents()
check("not composing after Cmd+A", not e._composing)
e.close()


# ============================================================
print("\n=== 7. Arrow keys while composing ===")
e = make_editor()
type_str(e, "sal")
check("popup visible while composing", e._popup.isVisible())
# Left arrow — should commit and move cursor, not navigate popup
press(e, Qt.Key_Left)
check("not composing after Left arrow", not e._composing)
e.close()


# ============================================================
print("\n=== 8. Enter creates new paragraph ===")
e = make_editor()
type_str(e, "salam ")
check("first word accepted", "سلام" in e.toPlainText())
press(e, Qt.Key_Return)
type_str(e, "kifach ")
text = e.toPlainText()
check("two paragraphs", "\n" in text, repr(text))
check("both words in text", "سلام" in text and "كيفاش" in text, text)
e.close()


# ============================================================
print("\n=== 9. Popup hides on Escape, Latin stays ===")
e = make_editor()
type_str(e, "sala")
check("popup visible", e._popup.isVisible())
press(e, Qt.Key_Escape)
check("popup hidden after Escape", not e._popup.isVisible())
check("still composing (Latin stays)", e._composing)
check("token still 'sala'", e._compose_token == "sala", e._compose_token)
e.close()


# ============================================================
print("\n=== 10. Standalone number stays as digit ===")
e = make_editor()
type_str(e, "3 ")
text = e.toPlainText()
check("'3 ' → digit stays (٣ or 3)", "3 " in text or "٣" in text, text)
e.close()


# ============================================================
print("\n=== 11. Number in word = Arabic letter ===")
e = make_editor()
type_str(e, "3lash ")
text = e.toPlainText()
check("ع in result (3 = ع)", "ع" in text, text)
e.close()


# ============================================================
print("\n=== 12. Punctuation: all PUNCT_MAP chars ===")
for latin, arabic in [(",", "،"), ("?", "؟"), (";", "؛")]:
    e = make_editor()
    type_str(e, "salam")
    highlighted = e._popup.current_text()
    if latin == "?":
        QTest.keyClick(e, Qt.Key_Question, Qt.ShiftModifier)
    else:
        QTest.keyClicks(e, latin)
    app.processEvents(); QTest.qWait(30)
    text = e.toPlainText()
    check(f"'{latin}' → '{arabic}' and arabic accepted",
          arabic in text and (highlighted or "") in text, text)
    e.close()


# ============================================================
print("\n=== 13. Passthrough punctuation (. ! : ) ===")
for ch in [".", "!", ":"]:
    e = make_editor()
    type_str(e, "salam")
    highlighted = e._popup.current_text()
    QTest.keyClicks(e, ch)
    app.processEvents(); QTest.qWait(30)
    text = e.toPlainText()
    check(f"'{ch}' stays as-is + arabic accepted",
          ch in text and (highlighted or "") in text, text)
    e.close()


# ============================================================
print("\n=== 14. Backspace chain: word → punct → word ===")
e = make_editor()
type_str(e, "salam.")
check("committed with .", not e._composing)
press(e, Qt.Key_Backspace)  # delete .
check("composing reopened after backspace over .", e._composing, e._compose_token)
press(e, Qt.Key_Escape)     # dismiss, keep Latin
press(e, Qt.Key_Space)      # commit (space = accept top Arabic)
type_str(e, "kifach")
check("can continue typing after backspace chain", e._compose_token == "kifach",
      e._compose_token)
e.close()


# ============================================================
print("\n=== 15. Paste Arabic text ===")
e = make_editor()
from PySide6.QtWidgets import QApplication as _QApp
_QApp.clipboard().setText("سلام عليكم")
# On macOS, Qt.ControlModifier = Command key = paste shortcut
QTest.keyClick(e, Qt.Key_V, Qt.ControlModifier)
app.processEvents(); QTest.qWait(50)
text = e.toPlainText()
check("pasted Arabic text present", "سلام" in text, text)
e.close()


# ============================================================
print("\n=== 16. Session learning (with in-memory DB) ===")
import sqlite3 as _sql
_db = _sql.connect(":memory:")
_db.row_factory = _sql.Row
_db.execute("CREATE TABLE choices (input TEXT NOT NULL, chosen TEXT NOT NULL, count INTEGER DEFAULT 1, last_used INTEGER, PRIMARY KEY(input, chosen))")
_db.commit()
from oktoboot import engine as _eng

e = make_editor()
e._learned_db = _db
type_str(e, "salam")
# Navigate to 3rd item (سلم)
press(e, Qt.Key_Down); press(e, Qt.Key_Down)
chosen = e._popup.current_text()
press(e, Qt.Key_Return)  # accept chosen
_eng.record_choice("salam", chosen, _db)
type_str(e, " salam")  # retype salam
QTest.qWait(50); app.processEvents()
learned = e._popup.current_text()
check("learned choice is now highlighted", learned == chosen, f"expected {chosen!r}, got {learned!r}")
e.close()


# ============================================================
print("\n=== 17. Shift+Space keeps Latin ===")
e = make_editor()
type_str(e, "iPhone")
check("composing 'iPhone'", e._composing)
QTest.keyClick(e, Qt.Key_Space, Qt.ShiftModifier)
app.processEvents(); QTest.qWait(30)
text = e.toPlainText()
check("Shift+Space keeps Latin 'iPhone'", "iPhone" in text, text)
e.close()


# ============================================================
print("\n=== 18. URL not transliterated ===")
e = make_editor()
type_str(e, "http://example.com ")
text = e.toPlainText().strip()
# URL might be partially committed but should not be fully transliterated
check("URL contains 'http'", "http" in text.lower(), text)
e.close()


# ============================================================
print(f"\n{'='*50}")
print(f"{PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
