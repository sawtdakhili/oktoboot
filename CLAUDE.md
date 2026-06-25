# oktoboot

Offline Arabic Arabizi/Franco-Arab text editor. See memory for full context.

**Launch:** `PYTHONPATH=src .venv/bin/python src/oktoboot/main.py`

**Test all:** `PYTHONPATH=src .venv/bin/python tests/test_engine.py && PYTHONPATH=src .venv/bin/python tests/test_editor.py && PYTHONPATH=src .venv/bin/python tests/test_comprehensive.py && PYTHONPATH=src .venv/bin/python tests/test_extended.py`

**Rebuild data:** `python3 scripts/build_frequencies.py && python3 scripts/build_doda.py`

**Rebuild icon:** `python3 scripts/build_icon.py` — renders `data/icon.svg` once at high res, strips the SVG's opaque white canvas (flood-fill the corners → transparent; a large threshold is needed or the anti-aliased white→dark gradient survives as a pale halo on the rounded corners), boosts contrast, then downscales (LANCZOS) into `data/icon.iconset/*` and writes `data/icon.icns`. (Don't run raw `rsvg-convert`/`iconutil` on the SVG directly — that re-introduces the white corners and low contrast.)

Run tests before touching engine.py or editor.py — engine/comprehensive/extended suites must all pass (143+ tests; editor suite is slightly timing-dependent on Qt, expect 29–30/30).

**Next up:**
1. Status bar — save state + Arabizi mode indicator (`#42c6ff` cyan / `#ff2afc` pink dot)
2. Tabs — multiple open documents
3. Harakat/tashkil mode — vowel diacritics toggle
4. Screenshot for README — once UI is more complete, populate with a poem
5. Phase 5 — `.app` bundle via PyInstaller
