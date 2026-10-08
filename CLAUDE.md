# oktoboot

Offline Arabic Arabizi/Franco-Arab text editor. See memory for full context.

**Launch:** `PYTHONPATH=src .venv/bin/python src/oktoboot/main.py`

**Test all:** `PYTHONPATH=src .venv/bin/python tests/test_engine.py && PYTHONPATH=src .venv/bin/python tests/test_editor.py && PYTHONPATH=src .venv/bin/python tests/test_comprehensive.py && PYTHONPATH=src .venv/bin/python tests/test_extended.py && PYTHONPATH=src .venv/bin/python tests/test_darija_words.py`

**Rebuild data:** `python3 scripts/build_frequencies.py && python3 scripts/build_doda.py`

**Rebuild icon:** `python3 scripts/build_icon.py` — renders `data/icon.svg` once at high res, strips the SVG's opaque white canvas (flood-fill the corners → transparent; a large threshold is needed or the anti-aliased white→dark gradient survives as a pale halo on the rounded corners), boosts contrast, scales the tile down to ~80.5% of the canvas with transparent padding around it (matches how macOS's own icons sit in the Dock/Cmd+Tab switcher — without this the tile reads visibly oversized next to other apps), then downscales (LANCZOS) into `data/icon.iconset/*` and writes `data/icon.icns`. (Don't run raw `rsvg-convert`/`iconutil` on the SVG directly — that re-introduces the white corners, low contrast, and oversized tile. Also don't inset the tentacle/pen artwork *within* the tile — tried once, user rejected it, see memory.)

Run tests before touching engine.py or editor.py — engine/comprehensive/extended suites must all pass, and the Darija benchmark (`tests/test_darija_words.py`) must stay above its `MIN_TOP1` floor (~222 tests total: 24 engine + 38 comprehensive + 54 extended + ~106 editor (a couple of tests branch on live engine output, so the check count can vary by 1–2); editor suite is timing-dependent on Qt keystroke simulation, expect no more than 1–2 failures — a failure is only a real regression if it reproduces on rerun, since dropped/duplicated simulated keystrokes are a known flake, not app behavior).

Plain Tab with no popup open inserts a literal tab character (Qt's default `QTextEdit` behavior, intentionally left as-is) — user explicitly wants this; treats it as a "big space" / validation key rather than a bug. Don't re-add a Tab-swallowing fix without asking first — tried once 2026-07-14, reverted same day.

**Decisions:** `DECISIONS.md` — append-only; read it before changing engine ranking, saving, or data builds.

**Next up (ship before tabs/harakat — decided 2026-10-08, see DECISIONS.md):**
1. Package as `.app` (PyInstaller), unsigned
2. Release: zipped `.app` on GitHub Releases + cask in own tap `sawtdakhili/homebrew-tap`; README gets the "Open Anyway" steps (see DECISIONS.md)
3. After shipping: tabs, harakat/tashkil mode, README screenshot, `moustafa`→مصطفى gap
