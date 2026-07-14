"""
Native macOS sheet dialogs via AppKit's NSAlert.

Qt's own mechanism for this — give a QMessageBox a parent, set
Qt.WindowModal, and show it with .open() instead of .exec() — is documented
to produce a native sheet (sliding down attached to the title bar), but on
this PySide6/Qt6 build it renders as a plain centered dialog instead: no
title-bar attachment, no slide animation. NSAlert's
beginSheetModalForWindow_completionHandler_ is the actual API Preview/
TextEdit use, so this talks to AppKit directly rather than going through Qt.
"""
from __future__ import annotations

from typing import Callable, Sequence


def frontmost_ns_window():
    from AppKit import NSApp
    return NSApp.mainWindow() or (NSApp.windows()[0] if NSApp.windows() else None)


def show_sheet(
    ns_window,
    message: str,
    informative: str,
    buttons: Sequence[str],
    on_response: Callable[[str], None],
    style: str = "warning",
):
    """
    Show an NSAlert as a sheet on ns_window.

    `buttons` are added in order via addButtonWithTitle_ — Cocoa lays them
    out right-to-left in that add order, so the FIRST entry becomes the
    rightmost button and the default (Return-triggered) one. A button
    titled exactly "Cancel" is auto-bound to Escape by Cocoa regardless of
    position. Returns the NSAlert — the caller must keep a reference alive
    until on_response fires, or the completion handler may never run.
    """
    from AppKit import (
        NSAlert, NSAlertStyleWarning, NSAlertStyleInformational, NSAlertStyleCritical,
    )

    alert = NSAlert.alloc().init()
    alert.setMessageText_(message)
    if informative:
        alert.setInformativeText_(informative)
    style_map = {
        "warning": NSAlertStyleWarning,
        "informational": NSAlertStyleInformational,
        "critical": NSAlertStyleCritical,
    }
    alert.setAlertStyle_(style_map.get(style, NSAlertStyleWarning))
    for label in buttons:
        alert.addButtonWithTitle_(label)

    def completion(response) -> None:
        idx = int(response) - 1000  # NSAlertFirstButtonReturn == 1000
        if 0 <= idx < len(buttons):
            on_response(buttons[idx])

    alert.beginSheetModalForWindow_completionHandler_(ns_window, completion)
    return alert
