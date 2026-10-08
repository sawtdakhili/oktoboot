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
  - Scrolling to a suggestion then typing more letters pins it: the new
    list ranks candidates starting with that suggestion first
  - A half-typed word survives an app switch: the popup hides while the
    app is inactive and reappears (same word, same suggestions) as soon
    as the app is active again. An Escape-dismissed popup stays dismissed
    across a switch. Clicks on committed words right after refocus do NOT
    reopen their re-edit popup
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

# Folds letter-forms that commonly change when a word grows a suffix, so a
# pinned prefix (see ArabicEditor._pinned_prefix) can still match after the
# engine legitimately respells the earlier letters — e.g. ة becomes ت under
# a suffix (مدرسة → مدرستي), hamza carriers vary (أ/إ/آ → ا), ى becomes ي.
_FOLD_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا",
    "ى": "ي", "ة": "ت",
})

def _fold(s: str) -> str:
    return s.translate(_FOLD_MAP)

# Arabic letters that can be absorbed/dropped when a word grows past them
# (a vowel-carrying final letter turning into an internal short vowel) —
# used as the last-resort pin tier below. ى (alef maksura, U+0649) is a
# distinct codepoint from ي (yeh, U+064A) — both are weak finals and must
# be listed, or common continuations like دى→دار silently fall through.
_ABSORBABLE_FINALS = set("اويةأى")

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
        # True once the user has scrolled the highlight away from the
        # default — the editor uses this to pin their choice when they
        # keep typing (see ArabicEditor._pinned_prefix).
        self._user_navigated: bool = False

    # ------------------------------------------------------------------

    def populate(self, latin_token: str, candidates: list[str]) -> None:
        """`candidates` is the full ranked list (from engine.suggest()) —
        already includes the Latin token wherever it ranks. Index 0 is
        always the intended default highlight."""
        self._items = candidates
        self._latin_token = latin_token
        self._current_idx = 0
        self._user_navigated = False
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
        self._user_navigated = True
        self._list.setCurrentRow(self._current_idx)
        self._list.scrollToItem(self._list.item(self._current_idx))

    def was_navigated(self) -> bool:
        return self._user_navigated

    def select_item(self, text: str) -> bool:
        """Move the highlight to the row showing `text` — used to restore
        a user-scrolled selection after an app switch. Counts as user
        navigation (so typing more letters still pins it, same as if the
        user had scrolled here themselves). False if the item is gone."""
        for i in range(self._list.count()):
            if self._list.item(i).text() == text:
                self._current_idx = i
                self._user_navigated = True
                self._list.setCurrentRow(i)
                self._list.scrollToItem(self._list.item(i))
                return True
        return False

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
        # Suggestion the user scrolled to before typing more letters.
        # Candidates starting with it are ranked (and highlighted) first
        # on the next popup, so the chosen rendering of the earlier
        # letters is kept.
        self._pinned_prefix: str | None = None
        # True when the popup was open at the moment the app deactivated —
        # it's restored on reactivation (an Escape-dismissed popup is not).
        self._restore_popup_on_activate: bool = False
        # The suggestion the user had scrolled to when the app deactivated,
        # so the restored popup highlights it again instead of resetting to
        # the top item. None when the highlight was still the default.
        self._restore_highlight: str | None = None

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
    # Copy — carry RTL direction into plain-text paste targets. Qt's
    # default rich-text (HTML) clipboard flavor already marks each
    # paragraph dir='rtl', but a paste target that only reads the
    # plain-text flavor (or a mostly-empty secondary rich-text flavor
    # some apps prefer) gets no directional signal at all and may guess
    # left — confirmed live: oktoboot → TextEdit pasted left-aligned.
    # Every document here is always RTL (see _force_rtl /
    # _apply_rtl_to_current_block), so this applies unconditionally.

    RLM = "‏"  # Right-to-Left Mark — invisible, zero width

    def createMimeDataFromSelection(self):
        mime = super().createMimeDataFromSelection()
        if mime.hasText():
            marked = self.RLM + mime.text().replace("\n", "\n" + self.RLM)
            mime.setText(marked)
        return mime

    # ------------------------------------------------------------------
    # Paste / drop — plain text only. Rich text from a web page or another
    # app would bring its own colours, fonts and left-to-right paragraphs
    # into a document that's always plain RTL. The RTL marks our own copy
    # adds (above) are stripped so they don't pile up in saved files.

    def insertFromMimeData(self, source) -> None:
        if not source.hasText():
            return
        text = source.text().replace(self.RLM, "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        cursor = self.textCursor()
        cursor.beginEditBlock()  # one undo step for paste + formatting
        start = cursor.selectionStart()  # insertText replaces any selection
        cursor.insertText(text, QTextCharFormat())
        end = cursor.position()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        fmt = QTextBlockFormat()
        fmt.setAlignment(Qt.AlignLeft)       # = visual right for RTL
        fmt.setLayoutDirection(Qt.RightToLeft)
        cursor.mergeBlockFormat(fmt)
        cursor.endEditBlock()
        cursor.clearSelection()
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
                if (not mods & Qt.ShiftModifier and self._reedit_entry is None
                        and len(self._compose_token) > 1
                        and self._compose_token.endswith("'")):
                    # salam' + Space: closing quote, handled with the
                    # other word-enders (see _handle_char).
                    self._handle_char(" ")
                    return
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
            if mods & (Qt.AltModifier | Qt.ControlModifier):
                # Option+Backspace (delete word) / Cmd+Backspace (delete
                # to line start): finish any compose, then let Qt do the
                # real deletion instead of our one-character backspace.
                if self._reedit_entry is not None:
                    self._reset_compose_state()
                elif self._composing:
                    self._commit_latin()
                super().keyPressEvent(event)
                return
            self._handle_backspace()
            return

        # Enter with no popup
        if key in (Qt.Key_Return, Qt.Key_Enter) and not self._popup.isVisible():
            if self._composing:
                self._commit_latin()
            super().keyPressEvent(event)
            self._apply_rtl_to_current_block()
            return

        # Modifier keys alone (Shift, Alt, Cmd/Ctrl) — don't commit. Checked
        # before the Cmd/Ctrl-held block below: macOS delivers a bare-Cmd
        # keydown (Key_Control, ControlModifier already set) the instant the
        # user presses Cmd to start Cmd+Tab, and that must NOT commit the
        # composing word — otherwise app-switch preservation (focusOutEvent,
        # _on_app_state_changed) never gets a chance to run, since the word
        # was already committed before focus was even lost.
        MODIFIERS = {
            Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta,
            Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
        }
        if key in MODIFIERS:
            super().keyPressEvent(event)
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

        # An apostrophe typed mid-word is a letter, not punctuation: the
        # engine maps 3'→غ, 9'→ض, 7'→خ, 6'→ظ, and a bare ' to ع/ء. Outside
        # a word (an opening quote) it stays punctuation, below.
        if ch == "'" and self._composing and not _looks_like_url(self._compose_token):
            self._begin_or_extend_compose(ch)
            return

        # Any word-ending character commits the composing word first
        if ch in WORD_ENDERS:
            if self._composing:
                token = self._compose_token
                closing_quote = (token.endswith("'") and len(token) > 1
                                 and self._reedit_entry is None)
                if closing_quote:
                    # salam' + space: the trailing ' was a closing quote,
                    # not a letter. Take it off the compose (and off the
                    # screen for now — the caret stays inside the compose
                    # range, so _on_cursor_moved doesn't fire a commit);
                    # it's re-inserted after the converted word below.
                    cursor = self.textCursor()
                    cursor.deletePreviousChar()
                    self.setTextCursor(cursor)
                    token = token[:-1]
                    self._compose_token = token
                # URL tokens stay Latin — no conversion
                if _looks_like_url(token):
                    choice = token
                elif self._popup.isVisible() and not closing_quote:
                    choice = self._popup.current_text() or token
                else:
                    candidates = engine.suggest(token, self._learned_db)
                    choice = candidates[0] if candidates else token
                self._accept_suggestion(choice)
                if closing_quote:
                    self._insert_char("'")

            # Insert either the Arabic equivalent or the char as-is
            self._insert_char(PUNCT_MAP.get(ch, ch))
            return

        self._begin_or_extend_compose(ch)

    def _begin_or_extend_compose(self, ch: str) -> None:
        # Reset blink on keystroke so cursor stays visible while typing
        self._cursor_visible = True
        self._cursor_timer.start()
        # Typing after scrolling to a suggestion pins that suggestion:
        # the extended word's candidates keep it as their start.
        if self._composing and self._popup.isVisible() and self._popup.was_navigated():
            self._pinned_prefix = self._popup.current_text()
        if self._composing and self._reedit_entry is not None:
            # Typing into a reopened word: edit its Latin, not the Arabic.
            # If the word went stale, fall through to a fresh compose.
            self._reedit_to_latin()
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

        # Keep candidates matching the pinned suggestion first (stable),
        # so the rendering the user scrolled to stays highlighted as the
        # word grows. The engine often legitimately respells the earlier
        # letters once the word is longer (ة→ت under a suffix, hamza
        # carrier swaps, a vowel-carrying final letter absorbed into an
        # internal vowel) — an exact match would silently lose the pin in
        # those cases, so three progressively looser tiers are tried in
        # order and the first one with any hits wins. No hits in any tier
        # falls back to the engine's own order.
        if self._pinned_prefix:
            pin = self._pinned_prefix
            # (matcher, needle) pairs, loosest match tried only if tighter
            # ones find nothing:
            #   1. exact prefix match
            #   2. letter-form folded on both sides (ة/ت, hamza carriers, ى/ي)
            #   3. folded, with the pin's absorbable final letter dropped
            #      (a vowel-carrying final letter turning into an internal
            #      short vowel as the word grows, e.g. مو → مصطفى)
            tiers = [
                (lambda c: c, pin),
                (_fold, _fold(pin)),
            ]
            if len(pin) >= 2 and pin[-1] in _ABSORBABLE_FINALS:
                tiers.append((_fold, _fold(pin[:-1])))

            pinned: list[str] = []
            for fold_fn, needle in tiers:
                pinned = [c for c in candidates if fold_fn(c).startswith(needle)]
                if pinned:
                    break

            if pinned:
                rest = [c for c in candidates if c not in pinned]
                candidates = pinned + rest

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

    def _reedit_to_latin(self) -> bool:
        """
        First real edit (a typed letter or a backspace) during a re-edit:
        swap the committed word back to its Latin token on screen, then
        continue as a fresh compose, so the keystroke edits Latin letters,
        never the Arabic word itself. Just reopening a word (click, or
        backspace over the following space) and then leaving or escaping
        doesn't call this, so the word stays untouched.

        False if the word no longer matches what's in the document (e.g.
        an intervening undo): the re-edit is cancelled and nothing changes.
        """
        entry = self._reedit_entry
        if entry is None:
            return True
        if not entry.is_valid():
            self._reset_compose_state()
            return False
        start, end, latin = entry.start(), entry.end(), entry.latin
        self._remove_words_overlapping(start, end)
        # State first: the text swap below moves the caret, and
        # _on_cursor_moved must already see a fresh compose over [start,
        # start+len(latin)] or it would commit/cancel mid-swap.
        self._reedit_entry = None
        self._compose_start = start
        self._compose_token = latin
        swap = QTextCursor(self.document())
        swap.setPosition(start)
        swap.setPosition(end, QTextCursor.KeepAnchor)
        swap.insertText(latin)
        caret = self.textCursor()
        caret.setPosition(start + len(latin))
        self.setTextCursor(caret)
        return True

    def _reset_compose_state(self) -> None:
        self._composing = False
        self._compose_start = -1
        self._compose_token = ""
        self._reedit_entry = None
        self._pinned_prefix = None
        self._restore_popup_on_activate = False
        self._restore_highlight = None
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
        # Accepting a word that already has a space after it (re-editing
        # mid-sentence): step over that space instead of doubling it.
        cursor = self.textCursor()
        if self.document().characterAt(cursor.position()) == " ":
            cursor.movePosition(QTextCursor.NextCharacter)
            self.setTextCursor(cursor)
            return
        self._insert_char(" ")

    # ------------------------------------------------------------------
    # Backspace

    def _handle_backspace(self) -> None:
        if not self._arabizi_enabled:
            super().keyPressEvent(
                QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Backspace, Qt.NoModifier)
            )
            return

        if self._composing and self._reedit_entry is not None:
            # Backspace into a reopened word: edit its Latin, never delete
            # a letter of the Arabic word. A stale word just cancels.
            if not self._reedit_to_latin():
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
        # Switching to another app (Cmd+Tab, clicking another window)
        # keeps the half-typed word composing — and remembers that its
        # popup was open, so _on_app_state_changed can restore it on
        # return. Captured here, not in _on_app_state_changed: this
        # focus-out fires (and hides the popup) BEFORE the app-state
        # signal, so sampling isVisible() there would always see False.
        # Losing focus to something inside the app still commits.
        if event.reason() in (Qt.ActiveWindowFocusReason, Qt.PopupFocusReason):
            if self._popup.isVisible() and self._composing:
                self._restore_popup_on_activate = True
                if self._popup.was_navigated():
                    self._restore_highlight = self._popup.current_text()
        else:
            if self._composing:
                self._commit_latin()
        self._popup.hide()
        self._was_focused = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        first_click_after_refocus = not self._was_focused
        self._was_focused = True
        if first_click_after_refocus and self._composing:
            # The click that brings the window back while a half-typed
            # word is pending: swallow it and put the caret back at the
            # end of the compose. Letting it through would reposition
            # the cursor, and _on_cursor_moved would commit the word —
            # exactly the "came back and my letters were forgotten"
            # bug. A deliberate second click still moves the caret
            # (and commits) as usual.
            end = (self._reedit_entry.end() if self._reedit_entry is not None
                   else self._compose_start + len(self._compose_token))
            cursor = self.textCursor()
            cursor.setPosition(end)
            self.setTextCursor(cursor)
            event.accept()
            return
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
            # Hide the popup but keep the compose state — the half-typed
            # word (and its popup, restored below) survive the app switch.
            # _restore_popup_on_activate was captured in focusOutEvent
            # (which fires first); it distinguishes "hidden because we
            # switched away" from "user dismissed it with Escape before
            # switching" — only the former is restored on return.
            if self._popup.isVisible() and self._composing:
                self._restore_popup_on_activate = True
                if self._popup.was_navigated():
                    self._restore_highlight = self._popup.current_text()
            self._popup.hide()
        else:
            if (self._restore_popup_on_activate
                    and self._composing and self._compose_token
                    and not _looks_like_url(self._compose_token)):
                self._show_popup()
                if self._restore_highlight:
                    self._popup.select_item(self._restore_highlight)
            self._restore_popup_on_activate = False
            self._restore_highlight = None

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
