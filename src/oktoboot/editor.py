"""
ArabicEditor — QTextEdit subclass with Arabizi inline transliteration.

Interaction model (Yamli-parity):
  - Typing Latin chars builds a "composing token" shown in the text as-is
  - Popup appears below the cursor showing the ranked suggestion list; the
    raw Latin token is one of the candidates (styled italic/gray), ranked
    by the same three-tier system as everything else — not a fixed slot
  - Space        → accept highlighted suggestion + insert space
  - Shift+Space  → accept raw Latin + insert space
  - Enter / Tab  → accept highlighted suggestion (no space)
  - Escape       → dismiss popup, keep Latin in place
  - Up / Down    → scroll through popup (all candidates, no "more" link)
  - Click item   → accept that suggestion
  - Backspace    → remove last composing char, update popup
  - Popup hides when app loses focus; does NOT reopen on refocus click
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass

from PySide6.QtCore import (
    QPoint, QRect, Qt, QTimer, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QKeyEvent, QLinearGradient, QMouseEvent, QPainter,
    QPen, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QLabel, QListWidget, QListWidgetItem,
    QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)

from oktoboot import engine

# ---------------------------------------------------------------------------
# Punctuation auto-conversion
# ---------------------------------------------------------------------------

# Characters that are converted to their Arabic equivalents
PUNCT_MAP = {
    ",": "،",
    "?": "؟",
    ";": "؛",
}

# Characters that commit the current word AND are inserted as-is (no conversion)
PUNCT_PASSTHROUGH = set("!.:()-/\"'@#%$*")

WORD_SEPARATORS = set(" \t\n\r")

# All characters that end a composing word (union of above)
WORD_ENDERS = set(PUNCT_MAP.keys()) | PUNCT_PASSTHROUGH | WORD_SEPARATORS

URL_PREFIXES = ("http://", "https://", "www.")

def _looks_like_url(token: str) -> bool:
    """True if token looks like a URL or the beginning of one."""
    t = token.lower()
    return (
        t.startswith("http") or t.startswith("www") or
        "://" in t or t.startswith("ftp")
    )

# Max visible rows in popup before scroll kicks in
POPUP_MAX_ROWS = 6
POPUP_ROW_HEIGHT = 34
POPUP_MAX_WIDTH = 320   # cap so long words don't make popup span the window


# ---------------------------------------------------------------------------
# Committed-word tracking
# ---------------------------------------------------------------------------

@dataclass
class CommittedWord:
    """Tracks a committed word so it can be re-edited (clicked, or reached
    via backspace) later.

    `cursor` is a QTextCursor holding a selection over the word. Qt shifts a
    live QTextCursor's positions automatically as surrounding text changes,
    so `start()`/`end()` always reflect where the word actually is now — no
    stale integer offsets. An entry is only trusted if its live selection
    still matches `text`; anything else (an undo, an edit landing inside the
    word, etc.) invalidates it instead of risking a corrupt replacement.
    """
    cursor: QTextCursor
    latin: str
    text: str

    def is_valid(self) -> bool:
        return bool(self.text) and self.cursor.selectedText() == self.text

    def start(self) -> int:
        return self.cursor.selectionStart()

    def end(self) -> int:
        return self.cursor.selectionEnd()


# ---------------------------------------------------------------------------
# Suggestion Popup
# ---------------------------------------------------------------------------

class SuggestionPopup(QFrame):
    """
    Floating suggestion list. Shows ALL candidates in a scrollable list.
    No "plus de choix" — arrow keys scroll through everything.
    Hides when the app loses focus.
    """

    item_chosen = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        # Child widget of the viewport — NOT a separate system window.
        # Stays inside the app, no floating window in the OS window list.
        super().__init__(parent)
        self.setWindowFlags(Qt.Widget)  # ensure it's treated as a regular child
        self.setStyleSheet("""
            SuggestionPopup {
                background: #131033;
                border: 1px solid #2d2844;
                border-radius: 6px;
            }
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                color: #f2f3f7;
                padding: 6px 20px;
            }
            QListWidget::item:selected {
                background: #BA45A3;
                color: #f2f3f7;
            }
            QListWidget::item:hover {
                background: #2d2844;
            }
            QScrollBar:vertical {
                background: #0c0a20;
                width: 4px;
                border-radius: 2px;
            }
            QScrollBar::handle:vertical {
                background: #2d2844;
                border-radius: 2px;
                min-height: 16px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        self._items: list[str] = []
        self._latin_token: str = ""
        self._current_idx: int = 0

    # ------------------------------------------------------------------

    def populate(self, latin_token: str, candidates: list[str]) -> None:
        """`candidates` is the full ranked list (from engine.suggest()) —
        already includes the Latin token wherever it ranks. Index 0 is
        always the intended default highlight."""
        self._items = candidates
        self._latin_token = latin_token
        self._current_idx = 0
        self._rebuild()

    def _rebuild(self) -> None:
        self._list.clear()
        for text in self._items:
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if text == self._latin_token:
                f = self._list.font()
                f.setItalic(True)
                item.setFont(f)
                item.setForeground(Qt.gray)  # type: ignore[arg-type]
            self._list.addItem(item)

        self._resize()
        self._clamp()
        # Apply selection after resize so layout is stable
        if 0 <= self._current_idx < self._list.count():
            self._list.setCurrentRow(self._current_idx)
            self._list.scrollToItem(self._list.item(self._current_idx))

    def _resize(self) -> None:
        n = min(len(self._items), POPUP_MAX_ROWS)
        h = n * POPUP_ROW_HEIGHT + 8
        # Cap width — never wider than POPUP_MAX_WIDTH regardless of content length
        w = min(POPUP_MAX_WIDTH, max(180, self._list.sizeHintForColumn(0) + 40))
        self.setFixedSize(w, h)

    def _clamp(self) -> None:
        n = self._list.count()
        if n > 0:
            self._current_idx = max(0, min(self._current_idx, n - 1))

    # ------------------------------------------------------------------

    def move_selection(self, delta: int) -> None:
        n = self._list.count()
        if not n:
            return
        self._current_idx = (self._current_idx + delta) % n
        self._list.setCurrentRow(self._current_idx)
        self._list.scrollToItem(self._list.item(self._current_idx))

    def current_text(self) -> str | None:
        item = self._list.currentItem()
        return item.text() if item else None

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self.item_chosen.emit(item.text())

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        # Fade-to-transparent gradient at the bottom when list is scrollable
        if len(self._items) > POPUP_MAX_ROWS:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            fade_h = POPUP_ROW_HEIGHT
            r = self.rect()
            grad = QLinearGradient(0, r.bottom() - fade_h, 0, r.bottom())
            c_transparent = QColor("#131033"); c_transparent.setAlpha(0)
            c_solid = QColor("#131033"); c_solid.setAlpha(220)
            grad.setColorAt(0.0, c_transparent)
            grad.setColorAt(1.0, c_solid)
            painter.fillRect(r.left(), r.bottom() - fade_h, r.width(), fade_h, grad)
            painter.end()

    def show_at(self, viewport_pos: QPoint) -> None:
        """Position relative to parent (viewport) and show."""
        self.move(viewport_pos)
        self.show()
        self.raise_()


# ---------------------------------------------------------------------------
# Main editor widget
# ---------------------------------------------------------------------------

class ArabicEditor(QTextEdit):
    """RTL plain-text editor with inline Arabizi transliteration."""

    content_changed = Signal()
    arabizi_enabled_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None,
                 learned_db: sqlite3.Connection | None = None) -> None:
        super().__init__(parent)
        self._learned_db = learned_db
        self._font_size: int = 22
        self._arabizi_enabled: bool = True

        # ------------------------------------------------------------------
        # RTL setup
        # setAlignment() is the reliable way — sets current paragraph alignment
        # and new paragraphs inherit it. Must be called after show().
        self.setLayoutDirection(Qt.RightToLeft)
        # Queue RTL apply after the widget is fully constructed
        QTimer.singleShot(0, self._force_rtl)

        # ------------------------------------------------------------------
        # Composing state
        self._composing: bool = False
        self._compose_start: int = -1
        self._compose_token: str = ""
        # Set when re-editing a previously committed word (via click or
        # backspace-over-separator); None for a fresh compose.
        self._reedit_entry: CommittedWord | None = None

        # Committed words, tracked with self-adjusting cursors (see
        # CommittedWord) so re-edit positions stay correct as surrounding
        # text changes.
        self._words: list[CommittedWord] = []

        # Focus tracking — ignore first mouse click after refocus
        self._was_focused: bool = False

        # ------------------------------------------------------------------
        # Popup is a child of the viewport — stays inside the editor window
        self._popup = SuggestionPopup(self.viewport())
        self._popup.hide()
        self._popup.item_chosen.connect(self._accept_suggestion)

        self.document().contentsChanged.connect(self.content_changed)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        QApplication.instance().applicationStateChanged.connect(self._on_app_state_changed)

        # Hide Qt's native (white) caret so only our pink one shows; otherwise
        # the two blink on separate timers and the cursor flickers white+pink.
        self.setCursorWidth(0)

        # Blink timer for custom cursor
        self._cursor_visible = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(530)  # standard blink rate
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start()

    # ------------------------------------------------------------------
    # Custom cursor — pink in Arabizi mode, cyan in Latin mode, so the
    # active mode is visible right where the eye already is.

    CURSOR_COLOR_ARABIZI = QColor("#ff2afc")
    CURSOR_COLOR_LATIN = QColor("#42c6ff")
    CURSOR_WIDTH = 2

    def _blink_cursor(self) -> None:
        self._cursor_visible = not self._cursor_visible
        self.viewport().update(self.cursorRect())

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._was_focused = False
        self._cursor_visible = True
        self._cursor_timer.start()
        self.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.hasFocus() or not self._cursor_visible:
            return
        # Draw our own cursor (Qt's native caret is hidden via setCursorWidth(0))
        painter = QPainter(self.viewport())
        r = self.cursorRect()
        # Keep cursor inside viewport bounds
        x = max(0, min(r.x(), self.viewport().width() - self.CURSOR_WIDTH))
        color = self.CURSOR_COLOR_ARABIZI if self._arabizi_enabled else self.CURSOR_COLOR_LATIN
        painter.fillRect(x, r.y(), self.CURSOR_WIDTH, r.height(), color)
        painter.end()

    # ------------------------------------------------------------------
    # Public

    def set_learned_db(self, db: sqlite3.Connection) -> None:
        self._learned_db = db

    def set_font_size(self, size: int) -> None:
        self._font_size = max(10, min(48, size))
        f = self.font()
        f.setPointSize(self._font_size)
        self.setFont(f)

    def set_font_family(self, family: str) -> None:
        f = self.font()
        f.setFamily(family)
        self.setFont(f)

    def increase_font(self) -> None:
        self.set_font_size(self._font_size + 2)

    def decrease_font(self) -> None:
        self.set_font_size(self._font_size - 2)

    # ------------------------------------------------------------------
    # Arabizi on/off

    def set_arabizi_enabled(self, enabled: bool) -> None:
        if enabled == self._arabizi_enabled:
            return
        if not enabled and self._composing:
            # Finalize whatever's mid-flight before disabling: a fresh
            # compose's Latin chars are already on screen, so commit them;
            # a re-edit never touched its word, so just cancel cleanly.
            if self._reedit_entry is not None:
                self._reset_compose_state()
            else:
                self._commit_latin()
        self._arabizi_enabled = enabled
        self.viewport().update(self.cursorRect())  # repaint cursor in its new color
        self.arabizi_enabled_changed.emit(enabled)

    def toggle_arabizi_enabled(self) -> None:
        self.set_arabizi_enabled(not self._arabizi_enabled)

    # ------------------------------------------------------------------
    # RTL

    def _force_rtl(self) -> None:
        """
        Force RTL paragraph direction on all blocks.
        In Qt, AlignLeft = AlignLeading. For RTL paragraphs, the 'leading'
        edge is the RIGHT side. So AlignLeft puts text at the visual RIGHT.
        (AlignRight in RTL = visual LEFT — the opposite of what you'd expect.)
        """
        # Apply RTL block format to every block
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        fmt = QTextBlockFormat()
        fmt.setAlignment(Qt.AlignLeft)       # AlignLeft = leading edge = visual RIGHT for RTL
        fmt.setLayoutDirection(Qt.RightToLeft)
        cursor.setBlockFormat(fmt)
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)
        self.setTextCursor(cursor)
        self.setAlignment(Qt.AlignLeft)

    def _apply_rtl_to_current_block(self) -> None:
        cursor = self.textCursor()
        fmt = cursor.blockFormat()
        fmt.setAlignment(Qt.AlignLeft)
        fmt.setLayoutDirection(Qt.RightToLeft)
        cursor.setBlockFormat(fmt)
        self.setTextCursor(cursor)

    # ------------------------------------------------------------------
    # Key handling

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()
        text = event.text()

        # Shift+Tab toggles Arabizi mode. Checked first so it outranks the
        # popup's plain-Tab "accept suggestion" binding below. Qt reports
        # Shift+Tab as Key_Backtab (not Key_Tab + ShiftModifier) on most
        # platforms, so both forms are checked.
        if key == Qt.Key_Backtab or (key == Qt.Key_Tab and mods & Qt.ShiftModifier):
            self.toggle_arabizi_enabled()
            return

        # Font size shortcuts
        if mods & Qt.ControlModifier:
            if key in (Qt.Key_Equal, Qt.Key_Plus):
                self.increase_font()
                return
            if key == Qt.Key_Minus:
                self.decrease_font()
                return

        # Popup navigation
        if self._popup.isVisible():
            if key == Qt.Key_Down:
                self._popup.move_selection(1)
                return
            if key == Qt.Key_Up:
                self._popup.move_selection(-1)
                return
            if key == Qt.Key_Escape:
                if self._reedit_entry is not None:
                    # Re-editing: the underlying word was never modified,
                    # so a full clean reset is safe (no text change).
                    self._reset_compose_state()
                else:
                    self._dismiss_popup()
                return
            if key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
                choice = self._popup.current_text()
                if choice:
                    self._accept_suggestion(choice)
                return
            if key == Qt.Key_Space:
                if mods & Qt.ShiftModifier:
                    self._accept_suggestion(self._compose_token)
                else:
                    choice = self._popup.current_text()
                    if choice:
                        self._accept_suggestion(choice)
                self._insert_space()
                return

        # Backspace
        if key == Qt.Key_Backspace:
            self._handle_backspace()
            return

        # Enter with no popup
        if key in (Qt.Key_Return, Qt.Key_Enter) and not self._popup.isVisible():
            if self._composing:
                self._commit_latin()
            super().keyPressEvent(event)
            self._apply_rtl_to_current_block()
            return

        # If Cmd or Ctrl is held (shortcuts like Cmd+A, Cmd+V, Cmd+C, Cmd+Z),
        # commit composing word and let Qt handle the shortcut — never compose
        if mods & (Qt.ControlModifier | Qt.AltModifier):
            if self._composing:
                self._commit_latin()
            super().keyPressEvent(event)
            return

        # Printable character
        if text and text.isprintable():
            self._handle_char(text)
            return

        # Modifier keys alone (Shift, Alt, Cmd) — don't commit
        MODIFIERS = {
            Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
            Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
        }
        if key in MODIFIERS:
            super().keyPressEvent(event)
            return

        # Truly unknown key (arrows, Home, End, etc.) — commit then pass through
        if self._composing:
            self._commit_latin()
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Character dispatch

    def _handle_char(self, ch: str) -> None:
        if not self._arabizi_enabled:
            self._insert_char(ch)
            return

        # Any word-ending character commits the composing word first
        if ch in WORD_ENDERS:
            if self._composing:
                token = self._compose_token
                # URL tokens stay Latin — no conversion
                if _looks_like_url(token):
                    choice = token
                elif self._popup.isVisible():
                    choice = self._popup.current_text() or token
                else:
                    candidates = engine.suggest(token, self._learned_db)
                    choice = candidates[0] if candidates else token
                self._accept_suggestion(choice)

            # Insert either the Arabic equivalent or the char as-is
            self._insert_char(PUNCT_MAP.get(ch, ch))
            return

        self._begin_or_extend_compose(ch)

    def _begin_or_extend_compose(self, ch: str) -> None:
        # Reset blink on keystroke so cursor stays visible while typing
        self._cursor_visible = True
        self._cursor_timer.start()
        if not self._composing:
            self._composing = True
            self._compose_start = self.textCursor().position()
            self._compose_token = ""
            self._reedit_entry = None

        self._compose_token += ch
        self._insert_char(ch)

        # If token looks like a URL, bypass transliteration entirely
        if _looks_like_url(self._compose_token):
            self._popup.hide()
            return

        self._show_popup()

    # ------------------------------------------------------------------
    # Popup

    def _show_popup(self) -> None:
        if not self._compose_token:
            self._popup.hide()
            return

        candidates = engine.suggest(self._compose_token, self._learned_db)

        if not candidates:
            self._popup.hide()
            return

        self._popup.populate(self._compose_token, candidates)
        pos = self._cursor_viewport_pos()
        self._popup.show_at(pos)

    def _cursor_viewport_pos(self) -> QPoint:
        """Position in viewport coordinates for the popup."""
        rect: QRect = self.cursorRect()
        pt = rect.bottomLeft()
        # Nudge left so it doesn't clip the right edge on RTL
        popup_w = self._popup.width() if self._popup.width() > 10 else 240
        vp_w = self.viewport().width()
        x = min(pt.x(), vp_w - popup_w - 4)
        x = max(x, 4)
        return QPoint(x, pt.y() + 4)

    def _dismiss_popup(self) -> None:
        self._popup.hide()

    # ------------------------------------------------------------------
    # Committed-word tracking

    def _prune_words(self) -> None:
        self._words = [w for w in self._words if w.is_valid()]

    def _make_tracking_cursor(self, start: int, length: int) -> QTextCursor:
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(start + length, QTextCursor.KeepAnchor)
        # Without this, Qt's default behavior extends the selection to
        # swallow text inserted right at its edge (e.g. the space typed
        # right after a committed word), corrupting the tracked range.
        cursor.setKeepPositionOnInsert(True)
        return cursor

    def _remove_words_overlapping(self, start: int, end: int) -> None:
        self._words = [
            w for w in self._words if w.end() <= start or w.start() >= end
        ]

    def _word_at(self, pos: int) -> CommittedWord | None:
        """Committed word whose range contains `pos` (any click inside it)."""
        self._prune_words()
        for w in self._words:
            if w.start() <= pos <= w.end():
                return w
        return None

    def _word_ending_at(self, pos: int) -> CommittedWord | None:
        self._prune_words()
        for w in self._words:
            if w.end() == pos:
                return w
        return None

    def _reset_compose_state(self) -> None:
        self._composing = False
        self._compose_start = -1
        self._compose_token = ""
        self._reedit_entry = None
        self._popup.hide()

    # ------------------------------------------------------------------
    # Acceptance

    def _accept_suggestion(self, text: str) -> None:
        if not self._composing:
            return

        original_token = self._compose_token
        reedit = self._reedit_entry

        if reedit is not None and not reedit.is_valid():
            # The word we intended to re-edit no longer matches what's in
            # the document (e.g. an intervening undo) — abort without
            # touching text rather than risk replacing the wrong range.
            self._reset_compose_state()
            return

        if reedit is not None:
            start, end = reedit.start(), reedit.end()
        else:
            # Fresh compose — replace the Latin chars we inserted
            start = self._compose_start
            end = self._compose_start + len(self._compose_token)

        self._remove_words_overlapping(start, end)

        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(text)

        # Record learned choice — including "kept as Latin" (text ==
        # original_token via Shift+Space), so that preference ranks
        # accordingly next time through the same tier-3 mechanism as any
        # other choice (see engine.suggest()).
        if self._learned_db is not None:
            engine.record_choice(original_token, text, self._learned_db)

        # Track the newly committed word so it can be re-edited later
        tracking_cursor = self._make_tracking_cursor(start, len(text))
        self._words.append(CommittedWord(tracking_cursor, original_token, text))

        self._reset_compose_state()

    def _commit_latin(self) -> None:
        """Accept raw Latin without conversion."""
        if not self._composing:
            return

        if self._reedit_entry is None:
            # Fresh compose — the literal Latin chars are what's on screen;
            # track them so they can be re-clicked later.
            tracking_cursor = self._make_tracking_cursor(
                self._compose_start, len(self._compose_token)
            )
            self._words.append(
                CommittedWord(tracking_cursor, self._compose_token, self._compose_token)
            )
        # Re-editing: the original word was never modified on screen, so
        # its existing CommittedWord entry (if still valid) is left as-is.

        self._reset_compose_state()

    def _insert_char(self, ch: str) -> None:
        cursor = self.textCursor()
        cursor.insertText(ch)
        self.setTextCursor(cursor)

    def _insert_space(self) -> None:
        self._insert_char(" ")

    # ------------------------------------------------------------------
    # Backspace

    def _handle_backspace(self) -> None:
        if not self._arabizi_enabled:
            super().keyPressEvent(
                QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
            )
            return

        if self._composing and self._compose_token:
            # Remove last Latin composing char
            self._compose_token = self._compose_token[:-1]
            cursor = self.textCursor()
            cursor.deletePreviousChar()
            self.setTextCursor(cursor)
            if self._compose_token:
                self._show_popup()
            else:
                # Backspaced the whole token away. In a re-edit, the
                # underlying committed word was never touched (the cursor
                # sits before it), so a full reset safely abandons the
                # re-edit without clearing the still-valid entry.
                self._reset_compose_state()
            return

        # Not composing — check if just after a separator following a committed word
        # (space, punctuation ., , ! etc.)
        pos = self.textCursor().position()
        doc_text = self.toPlainText()
        if pos >= 1 and doc_text[pos - 1] in WORD_ENDERS | set("،؟؛"):
            cursor = self.textCursor()
            cursor.deletePreviousChar()
            self.setTextCursor(cursor)
            new_pos = self.textCursor().position()
            entry = self._word_ending_at(new_pos)
            if entry:
                self._composing = True
                self._compose_start = entry.start()
                self._compose_token = entry.latin
                self._reedit_entry = entry
                self._show_popup()
            return

        # Default: delete one character
        super().keyPressEvent(
            QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
        )

    # ------------------------------------------------------------------
    # Click — do NOT reopen popup on refocus click
    # (focusInEvent defined above in cursor section also sets _was_focused=False)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        if self._composing:
            self._commit_latin()
        self._popup.hide()
        self._was_focused = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        first_click_after_refocus = not self._was_focused
        self._was_focused = True
        super().mousePressEvent(event)
        if not first_click_after_refocus:
            # Only check re-edit on deliberate clicks (not refocus clicks)
            self._check_click_reopen()

    def _check_click_reopen(self) -> None:
        if self._composing:
            return
        pos = self.textCursor().position()
        entry = self._word_at(pos)
        if entry:
            self._composing = True
            self._compose_start = entry.start()
            self._compose_token = entry.latin
            self._reedit_entry = entry
            self._show_popup()

    # ------------------------------------------------------------------
    # App focus loss

    def _on_app_state_changed(self, state) -> None:
        from PySide6.QtCore import Qt as _Qt
        if state != _Qt.ApplicationActive:
            self._popup.hide()
            if self._composing:
                self._commit_latin()

    # ------------------------------------------------------------------
    # Cursor moved — hide popup if cursor left composing range

    def _on_cursor_moved(self) -> None:
        if not self._composing:
            return
        pos = self.textCursor().position()

        if self._reedit_entry is not None:
            start, end = self._reedit_entry.start(), self._reedit_entry.end()
            if pos < start or pos > end:
                # Cursor left the word being re-edited; its on-screen text
                # was never touched, so just cancel — nothing to commit.
                self._reset_compose_state()
            return

        end = self._compose_start + len(self._compose_token)
        if pos < self._compose_start or pos > end:
            # Cursor left the Latin chars we're composing; they're already
            # literally in the document, so finalize them as a committed
            # word instead of leaving them silently attached to a stale
            # compose_start (which caused corruption on later accepts).
            self._commit_latin()
