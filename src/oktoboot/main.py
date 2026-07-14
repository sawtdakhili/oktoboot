"""oktoboot — offline Arabic Arabizi editor."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QTimer
from PySide6.QtGui import (
    QAction, QActionGroup, QFont, QFontDatabase, QIcon, QKeySequence,
)
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from oktoboot import native_dialogs
from oktoboot.editor import ArabicEditor
from oktoboot.store import open_learned_db

DATA_DIR = Path(__file__).parent.parent.parent / "data"
FONT_DIR = DATA_DIR / "fonts"

# Arabic-friendly fonts offered in the Format > Font submenu, in priority
# order — same list _setup_font() auto-picks the default from. "serif" is
# Qt's generic engine fallback, not a real installed family, so it's kept
# unconditionally available rather than filtered against QFontDatabase.
#
# DecoType Naskh, Montaser Arabic, and Baghdad were dropped from this list —
# checked via fontTools cmap inspection, none of them have a glyph for ڭ
# (U+06AD, Moroccan gaf — the engine maps "g" to it as top choice). پ/ڤ
# (p/v) are fine in all of them; ڭ is the one gap, but it's core, frequent
# Darija, not an edge case, so offering those fonts here is a real trap.
# Only Amiri and Geeza Pro cover the full Darija set.
FONT_CHOICES = [
    "Amiri",
    "Geeza Pro",
    "serif",
]

# ---------------------------------------------------------------------------
# Colors (outrun-electric palette)
# ---------------------------------------------------------------------------

STYLE = """
QMainWindow {
    background: #0c0a20;
}
QTextEdit {
    background: #0c0a20;
    color: #f2f3f7;
    border: none;
    selection-background-color: #BA45A3;
    selection-color: #f2f3f7;
}
QMenuBar {
    background: #0c0a20;
    color: #546A90;
}
QMenuBar::item:selected {
    background: #131033;
}
QMenu {
    background: #131033;
    color: #f2f3f7;
    border: 1px solid #2d2844;
}
QMenu::item:selected {
    background: #BA45A3;
}
QScrollBar:vertical {
    background: #0c0a20;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #2d2844;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    AUTOSAVE_MS = 30_000

    def __init__(self) -> None:
        super().__init__()
        self.resize(900, 700)

        # Persisted preferences (font family/size across restarts)
        self._settings = QSettings("oktoboot", "oktoboot")

        # Kept alive while a native sheet (native_dialogs.show_sheet) is
        # showing — without a Python reference, the NSAlert can be GC'd
        # before its completion handler fires.
        self._active_sheet = None

        # Seamless title bar on macOS
        self._setup_title_bar()

        # Learned DB
        self._learned_db = open_learned_db()

        self._editor = ArabicEditor(learned_db=self._learned_db)
        self._current_file: Path | None = None
        self._is_dirty = False

        self.setCentralWidget(self._editor)
        self._update_window_title()

        self._setup_font()
        self._setup_menus()

        self._editor.content_changed.connect(self._on_content_changed)

        # Auto-save timer
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(self.AUTOSAVE_MS)
        self._autosave_timer.timeout.connect(self._autosave)
        self._autosave_timer.start()

        # Recovery file (for crash protection)
        self._recovery_path = Path.home() / "Library" / "Application Support" / "oktoboot" / "recovery.txt"
        self._recovery_path.parent.mkdir(parents=True, exist_ok=True)

        # Restoring recovery is deferred to after show() (see main()) — a
        # sheet needs its parent window already on screen to attach to.

        # ArabicEditor applies its initial RTL block formatting via its own
        # QTimer.singleShot(0, ...) (queued above, during its construction).
        # Qt's contentsChanged fires for that formatting-only change same as
        # a real edit, marking the document dirty before the user has typed
        # anything. Queued here — after that — to clear the false positive
        # once it's already fired, without racing it.
        QTimer.singleShot(0, self._clear_startup_dirty)

    def _clear_startup_dirty(self) -> None:
        self._is_dirty = False
        self._set_document_edited(False)

    def _update_window_title(self) -> None:
        """
        Native macOS document-window convention: the title bar shows just the
        filename (no app name — that's what the menu bar is for), and a real
        file gets a represented-filename proxy icon (draggable, Cmd-click for
        the path breadcrumb), same as TextEdit/Notes/Pages.
        """
        name = self._current_file.name if self._current_file else "Untitled"
        self.setWindowTitle(name)
        try:
            ns_window = native_dialogs.frontmost_ns_window()
            if ns_window:
                ns_window.setRepresentedFilename_(
                    str(self._current_file) if self._current_file else ""
                )
        except Exception:
            pass

    def _set_document_edited(self, edited: bool) -> None:
        """Native unsaved-changes indicator — the dot in the close button."""
        try:
            ns_window = native_dialogs.frontmost_ns_window()
            if ns_window:
                ns_window.setDocumentEdited_(edited)
        except Exception:
            pass

    # ------------------------------------------------------------------

    def _setup_title_bar(self) -> None:
        """
        Make the title bar seamless with the background.

        Strategy: setTitlebarAppearsTransparent_ WITHOUT fullSizeContentView.
        The title bar becomes transparent — the window background colour (#0c0a20)
        shows through it. The title bar still EXISTS natively so dragging works.
        Content starts below the title bar (no overlap), so no event conflicts.
        """
        import platform
        if platform.system() != "Darwin":
            return

        try:
            from AppKit import NSApp, NSColor, NSAppearance  # type: ignore

            ns_window = NSApp.mainWindow() or (NSApp.windows()[0] if NSApp.windows() else None)
            if not ns_window:
                return

            # Dark aqua so system controls (traffic lights etc.) use dark style
            ns_window.setAppearance_(
                NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua")
            )
            # Transparent title bar — window background colour shows through
            ns_window.setTitlebarAppearsTransparent_(True)
            # Keep title visible — shows filename (e.g. "untitled.md")
            # Set window background to our exact colour
            ns_window.setBackgroundColor_(
                NSColor.colorWithRed_green_blue_alpha_(
                    0x0c / 255, 0x0a / 255, 0x20 / 255, 1.0
                )
            )
            # No fullSizeContentView — content stays below title bar → native drag works
        except Exception:
            pass

    def _setup_font(self) -> None:
        available = QFontDatabase.families()
        default_family = next((f for f in FONT_CHOICES if f in available), "serif")
        family = self._settings.value("font/family", default_family)
        if family != "serif" and family not in available:
            family = default_family
        size = self._settings.value("font/size", 22, type=int)

        font = QFont(family, size)
        font.setStyleStrategy(QFont.PreferAntialias)
        self._editor.setFont(font)
        self._editor.set_font_size(size)  # syncs ArabicEditor._font_size bookkeeping

        # Cursor is custom-painted in ArabicEditor.paintEvent (pink/cyan by
        # mode); setCursorWidth(0) there hides Qt's native caret. Do NOT
        # set a nonzero cursor width here — it re-enables that native caret,
        # which then blinks on its own timer, out of sync with ours,
        # producing a white flicker alongside the real cursor.
        from PySide6.QtGui import QPalette, QColor
        palette = self._editor.palette()
        palette.setColor(QPalette.Text, QColor("#f2f3f7"))
        palette.setColor(QPalette.Base, QColor("#0c0a20"))
        palette.setColor(QPalette.Highlight, QColor("#BA45A3"))
        palette.setColor(QPalette.HighlightedText, QColor("#f2f3f7"))
        self._editor.setPalette(palette)

        # Padding via root frame margins — this is what cursor positions respect.
        # setViewportMargins only affects scroll area outer space, not document layout.
        from PySide6.QtGui import QTextFrameFormat
        fmt = self._editor.document().rootFrame().frameFormat()
        fmt.setLeftMargin(80)
        fmt.setRightMargin(80)
        fmt.setTopMargin(60)
        fmt.setBottomMargin(60)
        self._editor.document().rootFrame().setFrameFormat(fmt)

    def _increase_font(self) -> None:
        self._editor.increase_font()
        self._settings.setValue("font/size", self._editor._font_size)

    def _decrease_font(self) -> None:
        self._editor.decrease_font()
        self._settings.setValue("font/size", self._editor._font_size)

    def _set_font_family(self, family: str) -> None:
        self._editor.set_font_family(family)
        self._settings.setValue("font/family", family)

    def _setup_menus(self) -> None:
        menu = self.menuBar()

        # --- File menu ---
        file_menu = menu.addMenu("File")

        close_action = QAction("Close Window", self)
        close_action.setShortcut(QKeySequence.Close)   # Cmd+W
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)

        file_menu.addSeparator()

        new_action = QAction("New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_file)
        file_menu.addAction(new_action)

        open_action = QAction("Open…", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_file)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save As…", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_file_as)
        file_menu.addAction(save_as_action)

        # --- Format menu (Font family/size — standard macOS location,
        # matching TextEdit/Pages rather than tucking these under View) ---
        format_menu = menu.addMenu("Format")

        bigger = QAction("Bigger Text", self)
        bigger.setShortcut(QKeySequence("Ctrl+="))
        bigger.triggered.connect(self._increase_font)
        format_menu.addAction(bigger)

        smaller = QAction("Smaller Text", self)
        smaller.setShortcut(QKeySequence("Ctrl+-"))
        smaller.triggered.connect(self._decrease_font)
        format_menu.addAction(smaller)

        format_menu.addSeparator()

        font_menu = format_menu.addMenu("Font")
        available = QFontDatabase.families()
        current_family = self._editor.font().family()
        font_group = QActionGroup(self)
        font_group.setExclusive(True)
        for family in FONT_CHOICES:
            if family != "serif" and family not in available:
                continue
            label = "System Serif (fallback)" if family == "serif" else family
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(family == current_family)
            action.triggered.connect(lambda checked, fam=family: self._set_font_family(fam))
            font_group.addAction(action)
            font_menu.addAction(action)

        # --- View menu ---
        view_menu = menu.addMenu("View")

        # No QAction shortcut here — toggling is done via Shift+Tab in the
        # editor (see ArabicEditor.keyPressEvent). This menu item is a
        # visual indicator plus a mouse-clickable fallback.
        arabizi_action = QAction("Arabizi Mode", self)
        arabizi_action.setCheckable(True)
        arabizi_action.setChecked(True)
        arabizi_action.triggered.connect(self._editor.set_arabizi_enabled)
        self._editor.arabizi_enabled_changed.connect(arabizi_action.setChecked)
        view_menu.addAction(arabizi_action)

    # ------------------------------------------------------------------
    # Native sheets — see native_dialogs.py for why this bypasses Qt.

    def _warn(self, message: str, informative: str = "") -> None:
        self._active_sheet = native_dialogs.show_sheet(
            native_dialogs.frontmost_ns_window(), message, informative, ["OK"],
            on_response=lambda _: setattr(self, "_active_sheet", None),
        )

    # ------------------------------------------------------------------
    # File operations

    def _new_file(self) -> None:
        def proceed() -> None:
            self._editor.clear()
            self._current_file = None
            self._is_dirty = False
            self._update_window_title()
            self._set_document_edited(False)
        self._confirm_discard(proceed)

    def _open_file(self) -> None:
        def proceed() -> None:
            path, _ = QFileDialog.getOpenFileName(
                self, "Open", str(Path.home()),
                "Text files (*.md *.txt *.org);;All files (*)"
            )
            if path:
                self._load(Path(path))
        self._confirm_discard(proceed)

    def _load(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            self._editor.setPlainText(text)
            self._editor._force_rtl()
            self._current_file = path
            self._is_dirty = False
            self._update_window_title()
            self._set_document_edited(False)
        except Exception as e:
            self._warn("Could not open file", str(e))

    def _save_file(self) -> None:
        if self._current_file:
            self._write(self._current_file)
        else:
            self._save_file_as()

    def _save_file_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save As", str(Path.home()),
            "Markdown (*.md);;Plain text (*.txt);;Org mode (*.org);;All files (*)"
        )
        if path:
            p = Path(path)
            self._write(p)
            self._current_file = p
            self._update_window_title()

    def _write(self, path: Path) -> None:
        try:
            path.write_text(self._editor.toPlainText(), encoding="utf-8")
            # Backup
            path.with_suffix(path.suffix + ".bak").write_text(
                self._editor.toPlainText(), encoding="utf-8"
            )
            self._is_dirty = False
            self._update_window_title()
            self._set_document_edited(False)
        except Exception as e:
            self._warn("Could not save file", str(e))

    def _confirm_discard(self, on_confirmed) -> None:
        if not self._is_dirty:
            on_confirmed()
            return

        def handle(button: str) -> None:
            self._active_sheet = None
            if button == "Discard":
                on_confirmed()

        # "Cancel" added first -> rightmost + default (Return-bound); Cocoa
        # also auto-binds Escape to it regardless of position.
        self._active_sheet = native_dialogs.show_sheet(
            native_dialogs.frontmost_ns_window(),
            "You have unsaved changes.", "Discard them?",
            ["Cancel", "Discard"], handle,
        )

    # ------------------------------------------------------------------
    # Auto-save and crash recovery

    def _on_content_changed(self) -> None:
        self._is_dirty = True
        self._set_document_edited(True)
        # Write recovery file immediately
        try:
            self._recovery_path.write_text(
                self._editor.toPlainText(), encoding="utf-8"
            )
        except Exception:
            pass

    def _autosave(self) -> None:
        if self._is_dirty and self._current_file:
            self._write(self._current_file)

    def _try_restore_recovery(self) -> None:
        if not self._recovery_path.exists():
            return
        content = self._recovery_path.read_text(encoding="utf-8").strip()
        if not content:
            return

        def handle(button: str) -> None:
            self._active_sheet = None
            if button == "Yes":
                self._editor.setPlainText(content)
                self._editor._force_rtl()
                self._is_dirty = True
                self._set_document_edited(True)

        # "Yes" added first -> rightmost + default (Return-bound).
        self._active_sheet = native_dialogs.show_sheet(
            native_dialogs.frontmost_ns_window(),
            "Unsaved text from a previous session was found.", "Restore it?",
            ["Yes", "No"], handle, style="informational",
        )

    def _cleanup_recovery(self) -> None:
        try:
            if self._recovery_path.exists():
                self._recovery_path.unlink()
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        if not self._is_dirty:
            self._cleanup_recovery()
            event.accept()
            return

        event.ignore()  # sheet decides asynchronously; re-close() below if confirmed

        def handle(button: str) -> None:
            self._active_sheet = None
            if button == "Save":
                self._save_file()
                if not self._is_dirty:  # save succeeded
                    self._cleanup_recovery()
                    self.close()
            elif button == "Discard":
                self._is_dirty = False
                self._set_document_edited(False)
                self._cleanup_recovery()
                self.close()
            # Cancel: leave the window open, do nothing further

        name = self._current_file.name if self._current_file else "Untitled"
        # Added in Save, Cancel, Discard order -> Cocoa lays them out
        # right-to-left as Discard, Cancel, Save (Save rightmost + default).
        self._active_sheet = native_dialogs.show_sheet(
            native_dialogs.frontmost_ns_window(),
            f"Do you want to save the changes you made to “{name}”?",
            "Your changes will be lost if you don't save them.",
            ["Save", "Cancel", "Discard"], handle,
        )


# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("oktoboot")
    app.setStyleSheet(STYLE)

    # Register the bundled Amiri font — it's shipped in data/fonts/ but not
    # installed system-wide, so without this QFontDatabase.families() never
    # contains "Amiri" and _setup_font()'s auto-pick silently falls through
    # to DecoType Naskh, which (unlike Amiri) has no glyph for ڭ (U+06AD,
    # Moroccan gaf) or other Darija-specific letters.
    for font_path in FONT_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(font_path))

    icon_path = DATA_DIR / "icon.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    # Title bar must be called after show() so the NSWindow handle exists
    window._setup_title_bar()
    # Recovery-restore sheet also needs the window already on screen to
    # attach to (see MainWindow._try_restore_recovery).
    window._try_restore_recovery()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
