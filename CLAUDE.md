# oktoboot

Offline Arabic Arabizi/Franco-Arab text editor. See memory for full context.

**Launch:** `PYTHONPATH=src .venv/bin/python src/oktoboot/main.py`

**Test all:** `PYTHONPATH=src .venv/bin/python tests/test_engine.py && PYTHONPATH=src .venv/bin/python tests/test_editor.py && PYTHONPATH=src .venv/bin/python tests/test_comprehensive.py && PYTHONPATH=src .venv/bin/python tests/test_extended.py`

**Rebuild data:** `python3 scripts/build_frequencies.py && python3 scripts/build_doda.py`

**Rebuild icon:** `python3 scripts/build_icon.py` — renders `data/icon.svg` once at high res, strips the SVG's opaque white canvas (flood-fill the corners → transparent; a large threshold is needed or the anti-aliased white→dark gradient survives as a pale halo on the rounded corners), boosts contrast, scales the tile down to ~80.5% of the canvas with transparent padding around it (matches how macOS's own icons sit in the Dock/Cmd+Tab switcher — without this the tile reads visibly oversized next to other apps), then downscales (LANCZOS) into `data/icon.iconset/*` and writes `data/icon.icns`. (Don't run raw `rsvg-convert`/`iconutil` on the SVG directly — that re-introduces the white corners, low contrast, and oversized tile. Also don't inset the tentacle/pen artwork *within* the tile — tried once, user rejected it, see memory.)

Run tests before touching engine.py or editor.py — engine/comprehensive/extended suites must all pass (~206 tests total: 24 engine + 38 comprehensive + 54 extended + ~90 editor (a couple of tests branch on live engine output, so the check count can vary by 1–2); editor suite is timing-dependent on Qt keystroke simulation, expect no more than 1–2 failures — a failure is only a real regression if it reproduces on rerun, since dropped/duplicated simulated keystrokes are a known flake, not app behavior).

**Next up:**
1. Tabs — multiple open documents
2. Harakat/tashkil mode — vowel diacritics toggle
3. Screenshot for README — once UI is more complete, populate with a poem
4. Phase 5 — `.app` bundle via PyInstaller
5. `moustafa`→مصطفى gap — "ou" can't be absorbed as a short vowel; "mostafa" works
6. Tab key inserts a literal tab when no popup is open in Arabizi mode — lands at the far left of an RTL line (visually stranded), easy to trigger right after an app-switch return before the popup has repopulated. Surfaced 2026-07-14, not yet fixed. Likely fix: swallow bare Tab (no popup, Arabizi enabled, not composing) instead of passing it through, or reopen the popup for the word at the cursor. See [[project_editor_word_tracking]] for the app-switch/popup-restore work this surfaced during.
