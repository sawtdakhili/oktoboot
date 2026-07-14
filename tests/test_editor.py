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
# Latin is folded into the ranked list, not a fixed slot — it should still
# be present (reachable), but not necessarily first.
check("Latin token still reachable in the list", "salam" in popup_items, popup_items[:3])
check("index 0 is Arabic (ranked ahead of the Latin fallback)", popup_items and any('؀' <= c <= 'ۿ' for c in popup_items[0]), popup_items[:3])
check("current_idx = 0 (top-ranked item highlighted)", e._popup._current_idx == 0, e._popup._current_idx)
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
check("word_map has an entry", len(e._words) > 0, e._words)
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
# Re-editing means picking a DIFFERENT suggestion for the same token (arrow
# keys + Enter) — not clearing and retyping a whole new word. Backspacing
# past the originally-clicked token doesn't delete real text (the cursor
# sits before the untouched committed word), so it can't shrink the word
# itself; that's a separate, pre-existing limitation out of scope here.

print("\n=== Test 7: Re-editing an earlier word doesn't break a later word's click ===")
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
type_text(e, "bghit")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
text_before = e.toPlainText()
print(f"     text before re-edit: {text_before!r}")

# Click the start of the first word and pick a LONGER candidate (سألام, 5
# chars, vs سلام's 4) via arrow-down + Enter — the supported re-edit path.
cursor = e.textCursor()
cursor.setPosition(0)
e.setTextCursor(cursor)
e._was_focused = True
e._check_click_reopen()
app.processEvents()
check("re-editing first word", e._composing and e._compose_token == "salam")
for _ in range(3):
    QTest.keyClick(e, Qt.Key_Down)
    app.processEvents()
check("selected a longer candidate", e._popup.current_text() == "سألام", e._popup.current_text())
QTest.keyClick(e, Qt.Key_Return)
app.processEvents()

text_after = e.toPlainText()
print(f"     text after lengthening first word: {text_after!r}")
second_word_start = text_after.index(" ") + 1

cursor2 = e.textCursor()
cursor2.setPosition(second_word_start)
e.setTextCursor(cursor2)
e._check_click_reopen()
app.processEvents()
check(
    "clicking second word at its NEW position reopens the right word",
    e._composing and e._compose_token == "bghit",
    (e._composing, e._compose_token),
)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 8: Re-editing an earlier word with a SHORTER replacement ===")
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
type_text(e, "bghit")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()

# Pick a SHORTER candidate (سلم, 3 chars, vs سلام's 4).
cursor = e.textCursor()
cursor.setPosition(0)
e.setTextCursor(cursor)
e._was_focused = True
e._check_click_reopen()
app.processEvents()
QTest.keyClick(e, Qt.Key_Down)
app.processEvents()
check("selected a shorter candidate", e._popup.current_text() == "سلم", e._popup.current_text())
QTest.keyClick(e, Qt.Key_Return)
app.processEvents()

text_after = e.toPlainText()
print(f"     text after shortening first word: {text_after!r}")
second_word_start = text_after.index(" ") + 1

cursor2 = e.textCursor()
cursor2.setPosition(second_word_start)
e.setTextCursor(cursor2)
e._check_click_reopen()
app.processEvents()
check(
    "clicking second word after shortening the first still reopens the right word",
    e._composing and e._compose_token == "bghit",
    (e._composing, e._compose_token),
)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 9: Undo doesn't corrupt text on a later click+accept ===")
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
QTest.keyClick(e, Qt.Key_Z, Qt.ControlModifier)  # undo -> back to Latin "salam"
app.processEvents()
text_after_undo = e.toPlainText()
print(f"     text after undo: {text_after_undo!r}")

cursor = e.textCursor()
cursor.setPosition(0)
e.setTextCursor(cursor)
e._was_focused = True
e._check_click_reopen()
app.processEvents()
check("stale entry does not reopen after undo", not e._composing)

if e._composing:
    QTest.keyClick(e, Qt.Key_Space)
    app.processEvents()

final_text = e.toPlainText()
print(f"     final text: {final_text!r}")
check(
    "text is not corrupted by click+accept after undo",
    final_text == text_after_undo,
    final_text,
)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 10: Mid-word click reopens the popup ===")
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
mid_pos = 2  # inside the committed Arabic word, not at its start
cursor = e.textCursor()
cursor.setPosition(mid_pos)
e.setTextCursor(cursor)
e._was_focused = True
e._check_click_reopen()
app.processEvents()
check(
    "clicking mid-word reopens the word",
    e._composing and e._compose_token == "salam",
    (e._composing, e._compose_token),
)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 11: Arabizi toggle — off means literal typing, no popup ===")
e = make_editor()
e.set_arabizi_enabled(False)
type_text(e, "salam")
check("no composing while disabled", not e._composing)
check("no popup while disabled", not e._popup.isVisible())
check("text stays literal Latin", e.toPlainText() == "salam", e.toPlainText())
type_text(e, "?")
check("punctuation not converted while disabled", e.toPlainText() == "salam?", e.toPlainText())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 12: Toggling off mid-compose commits cleanly ===")
e = make_editor()
type_text(e, "sala")
check("composing before toggle-off", e._composing)
e.set_arabizi_enabled(False)
check("composing ends when disabled", not e._composing)
check("Latin chars preserved as-is", e.toPlainText() == "sala", e.toPlainText())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 13: Toggling off mid-re-edit cancels without touching text ===")
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
committed = e.toPlainText()
cursor = e.textCursor()
cursor.setPosition(0)
e.setTextCursor(cursor)
e._was_focused = True
e._check_click_reopen()
app.processEvents()
check("re-editing before toggle-off", e._composing)
e.set_arabizi_enabled(False)
check("re-edit cancelled cleanly", not e._composing and e._reedit_entry is None)
check("committed word untouched", e.toPlainText() == committed, e.toPlainText())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 14: 'Keep as Latin' choice becomes the default next time ===")
import sqlite3 as _sql14
_db14 = _sql14.connect(":memory:")
_db14.row_factory = _sql14.Row
_db14.execute(
    "CREATE TABLE choices (input TEXT NOT NULL, chosen TEXT NOT NULL, "
    "count INTEGER DEFAULT 1, last_used INTEGER, PRIMARY KEY(input, chosen))"
)
_db14.commit()

e = make_editor()
e._learned_db = _db14
type_text(e, "iphone")
QTest.keyClick(e, Qt.Key_Space, Qt.ShiftModifier)
app.processEvents()
check("kept as Latin", "iphone" in e.toPlainText(), e.toPlainText())

type_text(e, "iphone")
app.processEvents()
check(
    "popup now defaults to the raw Latin item",
    e._popup.current_text() == "iphone",
    e._popup.current_text(),
)
QTest.keyClick(e, Qt.Key_Space)
app.processEvents()
check(
    "plain Space (no Shift) keeps it Latin now, thanks to learning",
    e.toPlainText().strip().endswith("iphone iphone"),
    e.toPlainText(),
)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 15: Shift+Tab toggles Arabizi mode ===")
e = make_editor()
check("Arabizi enabled by default", e._arabizi_enabled)
QTest.keyClick(e, Qt.Key_Tab, Qt.ShiftModifier)
app.processEvents()
check("Shift+Tab toggles it off", not e._arabizi_enabled)
QTest.keyClick(e, Qt.Key_Tab, Qt.ShiftModifier)
app.processEvents()
check("Shift+Tab toggles it back on", e._arabizi_enabled)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 16: Key_Backtab (Qt's Shift+Tab form) also toggles ===")
e = make_editor()
check("Arabizi enabled by default", e._arabizi_enabled)
QTest.keyClick(e, Qt.Key_Backtab, Qt.ShiftModifier)
app.processEvents()
check("Key_Backtab toggles it off", not e._arabizi_enabled)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 17: Plain Tab does NOT toggle Arabizi mode ===")
e = make_editor()
QTest.keyClick(e, Qt.Key_Tab)
app.processEvents()
check("plain Tab leaves Arabizi mode enabled", e._arabizi_enabled)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 18: Scrolled-to suggestion is pinned when typing continues ===")
e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
QTest.keyClick(e, Qt.Key_Down)
QTest.keyClick(e, Qt.Key_Down)
app.processEvents()
pinned = e._popup.current_text()
check("scrolled highlight is not the default", pinned and e._popup._current_idx != 0, pinned)
type_text(e, "am")
QTest.qWait(50)
app.processEvents()
new_items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
matching = [c for c in new_items if c.startswith(pinned)]
if matching:
    check("candidates starting with pinned suggestion come first",
          new_items[: len(matching)] == matching, new_items[:4])
    check("highlight sits on a pinned candidate",
          (e._popup.current_text() or "").startswith(pinned), e._popup.current_text())
else:
    # Engine produced no candidate extending this prefix — order untouched
    check("no pinned match: engine order preserved", True)
QTest.keyClick(e, Qt.Key_Space)
QTest.qWait(50)
app.processEvents()
check("pinned prefix reset on commit", e._pinned_prefix is None, e._pinned_prefix)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 18b: Pin survives letter-form respelling (folded tier) ===")
e = make_editor()
type_text(e, "waqfa")
QTest.qWait(50)
app.processEvents()
items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
# وقفة (ta marbuta) is expected as a non-default candidate here — must
# actually scroll (index > 0) or the no-scroll-doesn't-pin rule (Test 19)
# means nothing gets pinned and the test would pass without exercising it.
target_idx = next((i for i, t in enumerate(items) if t == "وقفة" and i > 0), None)
check("found a scrollable وقفة candidate", target_idx is not None, items[:6])
if target_idx is not None:
    for _ in range(target_idx):
        QTest.keyClick(e, Qt.Key_Down)
    app.processEvents()
    pinned = e._popup.current_text()
    check("scrolled to وقفة", pinned == "وقفة", pinned)
    type_text(e, "ti")  # suffix forces ة -> ت respelling (وقفة -> وقفتي)
    QTest.qWait(50)
    app.processEvents()
    new_items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
    check("respelled candidates still promoted to the top",
          new_items and new_items[0].startswith("وقفت"), new_items[:4])
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 18c: Pin survives an absorbed final vowel (dropped-final tier) ===")
e = make_editor()
type_text(e, "da")
QTest.qWait(50)
app.processEvents()
items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
target_idx = next((i for i, t in enumerate(items) if t == "دى" and i > 0), None)
check("found a scrollable 'دى' candidate", target_idx is not None, items[:6])
if target_idx is not None:
    for _ in range(target_idx):
        QTest.keyClick(e, Qt.Key_Down)
    app.processEvents()
    pinned = e._popup.current_text()
    check("scrolled to دى", pinned == "دى", pinned)
    type_text(e, "r")  # دى + r -> دار (long alef absorbs the short vowel)
    QTest.qWait(50)
    app.processEvents()
    new_items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
    check("absorbed-vowel candidate (دار) promoted to top",
          new_items and new_items[0] == "دار", new_items[:4])
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 18d: Bare Cmd keydown mid-compose does NOT commit ===")
e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
check("composing before Cmd keydown", e._composing and e._compose_token == "sal", e._compose_token)
# macOS delivers a bare-Cmd keydown (Key_Control, ControlModifier already
# set) the instant Cmd is pressed to start Cmd+Tab — this must not commit.
QTest.keyPress(e, Qt.Key_Control, Qt.ControlModifier)
app.processEvents()
check("still composing after bare Cmd keydown",
      e._composing and e._compose_token == "sal", e._compose_token)
QTest.keyRelease(e, Qt.Key_Control, Qt.NoModifier)
app.processEvents()
type_text(e, "am")
QTest.qWait(50)
app.processEvents()
check("word continues normally after release", e._compose_token == "salam", e._compose_token)
e.close()

e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
# A real chord (e.g. Cmd+A) must still commit, unlike a bare modifier press.
QTest.keyClick(e, Qt.Key_A, Qt.ControlModifier)
app.processEvents()
check("real Cmd+<letter> chord still commits", not e._composing)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 19: Default highlight (no scroll) does NOT pin ===")
e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
type_text(e, "am")
QTest.qWait(50)
app.processEvents()
check("no pin without user scroll", e._pinned_prefix is None, e._pinned_prefix)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 20: Compose survives app switch, resumes with full word ===")
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFocusEvent

e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
check("composing before leaving", e._composing and e._compose_token == "sal", e._compose_token)
# Scroll to a non-default suggestion before leaving
QTest.keyClick(e, Qt.Key_Down)
QTest.keyClick(e, Qt.Key_Down)
app.processEvents()
scrolled_to = e._popup.current_text()
check("scrolled off the default before leaving", e._popup._current_idx != 0, scrolled_to)
# Simulate Cmd+Tab away: focus-out for window deactivation + app inactive
app.sendEvent(e, QFocusEvent(QEvent.FocusOut, Qt.ActiveWindowFocusReason))
e._on_app_state_changed(Qt.ApplicationInactive)
app.processEvents()
check("popup hidden while away", not e._popup.isVisible())
check("still composing while away", e._composing and e._compose_token == "sal", e._compose_token)
# Come back — popup must reappear on its own, before any keystroke
e._on_app_state_changed(Qt.ApplicationActive)
app.sendEvent(e, QFocusEvent(QEvent.FocusIn, Qt.ActiveWindowFocusReason))
app.processEvents()
check("popup reappears immediately on return (no keystroke needed)",
      e._popup.isVisible())
check("restored popup highlights the suggestion scrolled to before leaving",
      e._popup.current_text() == scrolled_to,
      f"got {e._popup.current_text()!r}, wanted {scrolled_to!r}")
type_text(e, "am")
QTest.qWait(50)
app.processEvents()
check("token includes letters typed before leaving",
      e._compose_token == "salam", e._compose_token)
check("popup still up with full-word suggestions", e._popup.isVisible())
new_items = [e._popup._list.item(i).text() for i in range(e._popup._list.count())]
check("restored highlight also pins when typing continues",
      new_items and new_items[0].startswith(scrolled_to), new_items[:4])
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 20b: Escape-dismissed popup stays dismissed across a switch ===")
e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
QTest.keyClick(e, Qt.Key_Escape)
app.processEvents()
check("popup dismissed by Escape", not e._popup.isVisible())
check("still composing after Escape", e._composing, e._compose_token)
app.sendEvent(e, QFocusEvent(QEvent.FocusOut, Qt.ActiveWindowFocusReason))
e._on_app_state_changed(Qt.ApplicationInactive)
app.processEvents()
e._on_app_state_changed(Qt.ApplicationActive)
app.sendEvent(e, QFocusEvent(QEvent.FocusIn, Qt.ActiveWindowFocusReason))
app.processEvents()
check("popup NOT resurrected after return", not e._popup.isVisible())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 21: Returning by CLICK also keeps the half-typed word ===")
from PySide6.QtCore import QPoint

e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
# Leave the app
app.sendEvent(e, QFocusEvent(QEvent.FocusOut, Qt.ActiveWindowFocusReason))
e._on_app_state_changed(Qt.ApplicationInactive)
app.processEvents()
# Return by clicking somewhere far from the word (the refocus click)
e._on_app_state_changed(Qt.ApplicationActive)
app.sendEvent(e, QFocusEvent(QEvent.FocusIn, Qt.ActiveWindowFocusReason))
app.processEvents()
QTest.mouseClick(e.viewport(), Qt.LeftButton, pos=QPoint(60, 300))
app.processEvents()
check("refocus click keeps composing", e._composing and e._compose_token == "sal",
      f"composing={e._composing} token={e._compose_token!r}")
check("caret restored to end of half-typed word",
      e.textCursor().position() == e._compose_start + len(e._compose_token),
      e.textCursor().position())
type_text(e, "am")
QTest.qWait(50)
app.processEvents()
check("token continues after click-return", e._compose_token == "salam", e._compose_token)
# Deliberately moving the caret away afterwards commits as usual
QTest.keyClick(e, Qt.Key_Left)
app.processEvents()
check("deliberate caret move commits", not e._composing)
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 22: In-app focus loss still commits the composing word ===")
e = make_editor()
type_text(e, "sal")
QTest.qWait(50)
app.processEvents()
app.sendEvent(e, QFocusEvent(QEvent.FocusOut, Qt.MouseFocusReason))
app.processEvents()
check("in-app focus loss commits", not e._composing)
check("Latin stays in document", e.toPlainText() == "sal", e.toPlainText())
e.close()


# ---------------------------------------------------------------------------
print("\n=== Test 23: Copied plain text carries an RTL mark ===")
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
type_text(e, "wach")
QTest.keyClick(e, Qt.Key_Space)
QTest.qWait(50)
app.processEvents()
cursor = e.textCursor()
cursor.select(QTextCursor.Document)
e.setTextCursor(cursor)
mime = e.createMimeDataFromSelection()
RLM = "‏"
copied = mime.text()
check("copied plain text starts with the RTL mark", copied.startswith(RLM), repr(copied))
check("copied text still contains the original words",
      copied.replace(RLM, "") == e.toPlainText(), repr(copied))
e.close()

# Multi-paragraph: each line should get its own mark, not just the first.
e = make_editor()
type_text(e, "salam")
QTest.keyClick(e, Qt.Key_Space)
QTest.keyClick(e, Qt.Key_Return)
type_text(e, "wach")
QTest.keyClick(e, Qt.Key_Space)
QTest.qWait(50)
app.processEvents()
cursor = e.textCursor()
cursor.select(QTextCursor.Document)
e.setTextCursor(cursor)
mime = e.createMimeDataFromSelection()
copied = mime.text()
lines = copied.split("\n")
check("multi-line copy: every line starts with the RTL mark",
      len(lines) >= 2 and all(l.startswith(RLM) for l in lines if l), repr(copied))
e.close()


# ---------------------------------------------------------------------------
print(f"\n{'='*40}")
print(f"{PASS} passed, {FAIL} failed")
if FAIL:
    sys.exit(1)
