"""Interactive editor behavior tests — simulates keystrokes and checks results."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtGui import QTextCursor

from oktoboot.editor import ArabicEditor

app = QApplication.instance() or QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)


def make_editor() -> ArabicEditor:
    e = ArabicEditor()
    e.resize(800, 600)
    e.show()
    e.setFocus()
    app.processEvents()
    # Allow singleShot RTL timer to fire
    QTest.qWait(50)
    app.processEvents()
    return e


def type_text(editor, text):
    for ch in text:
        QTest.keyClicks(editor, ch)
        app.processEvents()


PASS = 0
FAIL = 0

def check(label, condition, got=None):
    global PASS, FAIL
    if condition:
        print(f"  ✓ {label}")
        PASS += 1
    else:
        print(f"  ✗ {label}" + (f" — got {got!r}" if got is not None else ""))
        FAIL += 1


# ---------------------------------------------------------------------------
print("\n=== Test 1: RTL alignment ===")
e = make_editor()
# alignment() returns the current paragraph alignment
align = e.alignment()
# AlignLeft = AlignLeading = visual RIGHT for RTL paragraphs (Qt BiDi semantics)
check("editor uses AlignLeft (= visual right for RTL)", align == Qt.AlignLeft, align)

# Also verify cursor starts at right side
cursor_x = e.cursorRect().x()
vp_w = e.viewport().width()
check("cursor starts near right edge (RTL)", cursor_x > vp_w * 0.7, f"x={cursor_x} viewport={vp_w}")

type_text(e, "s")
QTest.qWait(50)
app.processEvents()
align_after = e.alignment()
check("alignment after typing still AlignLeft (RTL leading)", align_after == Qt.AlignLeft, align_after)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 2: Popup shows on typing ===")
e = make_editor()
type_text(e, "salam")
QTest.qWait(100)
app.processEvents()
check("composing after 'salam'", e._composing)
check("compose_token = 'salam'", e._compose_token == "salam", e._compose_token)
check("popup visible", e._popup.isVisible())
popup_items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
check("popup item 0 is Latin ('salam')", popup_items[0] == "salam" if popup_items else False, popup_items[:3])
check("popup item 1 is Arabic", len(popup_items) > 1 and any('؀' <= c <= 'ۿ' for c in popup_items[1]), popup_items[:3])
check("current_idx = 1 (first Arabic highlighted)", e._popup._current_idx == 1, e._popup._current_idx)
highlighted = e._popup.current_text()
check("highlighted item is Arabic", highlighted and any('؀' <= c <= 'ۿ' for c in highlighted), highlighted)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 3: Space accepts highlighted suggestion ===")
e = make_editor()
type_text(e, "salam")
QTest.qWait(50)
app.processEvents()
highlighted = e._popup.current_text()
type_text(e, " ")
QTest.qWait(50)
app.processEvents()
text = e.toPlainText()
check("after space, not composing", not e._composing)
check("text contains accepted Arabic", highlighted and highlighted in text, f"text={text!r}, highlighted={highlighted!r}")
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 4a: Comma accepts highlighted item ===")
e = make_editor()
type_text(e, "salam")
QTest.qWait(50)
app.processEvents()
highlighted = e._popup.current_text()
type_text(e, ",")
QTest.qWait(50)
app.processEvents()
text = e.toPlainText()
check("comma converted to ،", "،" in text, text)
check("arabic word accepted with comma", highlighted and highlighted in text, f"expected {highlighted!r} in {text!r}")
check("not composing after comma", not e._composing)
e.close()

print("\n=== Test 4b: Period accepts highlighted item (as-is) ===")
e = make_editor()
type_text(e, "salam")
QTest.qWait(50)
app.processEvents()
highlighted = e._popup.current_text()
type_text(e, ".")
QTest.qWait(50)
app.processEvents()
text = e.toPlainText()
print(f"     text after period: {text!r}, highlighted was: {highlighted!r}")
check("period stays as '.'", "." in text, text)
check("arabic word accepted with period", highlighted and highlighted in text, f"expected {highlighted!r} in {text!r}")
check("not composing after period", not e._composing)
e.close()

print("\n=== Test 4c: Backspace after period-committed word ===")
e = make_editor()
type_text(e, "salam.")
QTest.qWait(50)
app.processEvents()
check("not composing after period", not e._composing)
QTest.keyClick(e, Qt.Key_Backspace)
QTest.qWait(50)
app.processEvents()
print(f"     composing: {e._composing}, popup: {e._popup.isVisible()}")
check("composing reopened after backspace-over-period", e._composing)
check("popup visible after backspace-over-period", e._popup.isVisible())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 5: Backspace during composing updates popup ===")
e = make_editor()
type_text(e, "sala")
QTest.qWait(50)
app.processEvents()
check("composing 'sala'", e._compose_token == "sala", e._compose_token)
check("popup visible", e._popup.isVisible())
QTest.keyClick(e, Qt.Key_Backspace)
QTest.qWait(50)
app.processEvents()
check("compose_token = 'sal' after backspace", e._compose_token == "sal", e._compose_token)
check("popup still visible", e._popup.isVisible())
check("text = 'sal'", e.toPlainText() == "sal", e.toPlainText())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 6: Backspace after committed word reopens popup ===")
e = make_editor()
type_text(e, "salam ")
QTest.qWait(50)
app.processEvents()
committed_text = e.toPlainText()
print(f"     committed text: {committed_text!r}")
check("word was committed (not composing)", not e._composing)
check("word_map has an entry", len(e._word_map) > 0, e._word_map)
# Now backspace to delete the space
QTest.keyClick(e, Qt.Key_Backspace)
QTest.qWait(100)
app.processEvents()
print(f"     text after backspace: {e.toPlainText()!r}")
print(f"     composing: {e._composing}, token: {e._compose_token!r}")
print(f"     popup visible: {e._popup.isVisible()}")
check("composing re-entered after backspace", e._composing)
check("popup visible after backspace", e._popup.isVisible())
e.close()


# ---------------------------------------------------------------------------
print(f"\n{'='*40}")
print(f"{PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
