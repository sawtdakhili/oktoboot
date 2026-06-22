"""oktoboot — offline Arabic Arabizi editor."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QKeySequence, QAction
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QWidget,
)

from oktoboot.editor import ArabicEditor
from oktoboot.store import open_learned_db

DATA_DIR = Path(__file__).parent.parent.parent / "data"
FONT_DIR = DATA_DIR / "fonts"

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
        self.setWindowTitle("oktoboot")
        self.resize(900, 700)

        # Seamless title bar on macOS
        self._setup_title_bar()

        # Learned DB
        self._learned_db = open_learned_db()

        self._editor = ArabicEditor(learned_db=self._learned_db)
        self._current_file: Path | None = None
        self._is_dirty = False

        self.setCentralWidget(self._editor)
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

        # Restore recovery if exists
        self._try_restore_recovery()

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
        # Prefer Arabic serif fonts in priority order
        preferred = [
            "Amiri",          # if installed system-wide
            "DecoType Naskh", # system font on macOS — classical Arabic serif
            "Montaser Arabic",
            "Baghdad",
            "Geeza Pro",      # macOS system Arabic (sans but legible)
            "serif",
        ]
        available = QFontDatabase.families()
        family = next((f for f in preferred if f in available), "serif")

        font = QFont(family, 22)
        font.setStyleStrategy(QFont.PreferAntialias)
        self._editor.setFont(font)

        # Make the cursor visible — 2px wide, bright pink (Ghostty cursor colour)
        self._editor.setCursorWidth(2)
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

        # --- View menu ---
        view_menu = menu.addMenu("View")

        bigger = QAction("Bigger Text", self)
        bigger.setShortcut(QKeySequence("Ctrl+="))
        bigger.triggered.connect(self._editor.increase_font)
        view_menu.addAction(bigger)

        smaller = QAction("Smaller Text", self)
        smaller.setShortcut(QKeySequence("Ctrl+-"))
        smaller.triggered.connect(self._editor.decrease_font)
        view_menu.addAction(smaller)

    # ------------------------------------------------------------------
    # File operations

    def _new_file(self) -> None:
        if not self._confirm_discard():
            return
        self._editor.clear()
        self._current_file = None
        self._is_dirty = False
        self.setWindowTitle("oktoboot — Untitled")

    def _open_file(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open", str(Path.home()),
            "Text files (*.md *.txt *.org);;All files (*)"
        )
        if path:
            self._load(Path(path))

    def _load(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
            self._editor.setPlainText(text)
            self._editor._force_rtl()
            self._current_file = path
            self._is_dirty = False
            self.setWindowTitle(f"oktoboot — {path.name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not open file:\n{e}")

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
            self.setWindowTitle(f"oktoboot — {p.name}")

    def _write(self, path: Path) -> None:
        try:
            path.write_text(self._editor.toPlainText(), encoding="utf-8")
            # Backup
            path.with_suffix(path.suffix + ".bak").write_text(
                self._editor.toPlainText(), encoding="utf-8"
            )
            self._is_dirty = False
            self.setWindowTitle(f"oktoboot — {path.name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save file:\n{e}")

    def _confirm_discard(self) -> bool:
        if not self._is_dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved changes",
            "You have unsaved changes. Discard them?",
            QMessageBox.Discard | QMessageBox.Cancel,
        )
        return reply == QMessageBox.Discard

    # ------------------------------------------------------------------
    # Auto-save and crash recovery

    def _on_content_changed(self) -> None:
        self._is_dirty = True
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
        if self._recovery_path.exists():
            content = self._recovery_path.read_text(encoding="utf-8").strip()
            if content:
                reply = QMessageBox.question(
                    self, "Restore",
                    "Unsaved text from a previous session was found. Restore it?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    self._editor.setPlainText(content)
                    self._is_dirty = True

    def closeEvent(self, event) -> None:
        if self._is_dirty:
            reply = QMessageBox.question(
                self, "Save before closing?",
                "You have unsaved changes.",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Save:
                self._save_file()
                if self._is_dirty:  # save failed
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        # Clear recovery file on clean exit
        try:
            if self._recovery_path.exists():
                self._recovery_path.unlink()
        except Exception:
            pass
        event.accept()


# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("oktoboot")
    app.setStyleSheet(STYLE)

    icon_path = DATA_DIR / "icon.icns"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    window = MainWindow()
    window.show()
    # Title bar must be called after show() so the NSWindow handle exists
    window._setup_title_bar()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
