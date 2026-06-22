# oktoboot

Offline Arabic Arabizi/Franco-Arab text editor. See memory for full context.

**Launch:** `PYTHONPATH=src .venv/bin/python src/oktoboot/main.py`

**Test all:** `PYTHONPATH=src .venv/bin/python tests/test_engine.py && PYTHONPATH=src .venv/bin/python tests/test_editor.py && PYTHONPATH=src .venv/bin/python tests/test_comprehensive.py && PYTHONPATH=src .venv/bin/python tests/test_extended.py`

**Rebuild data:** `python3 scripts/build_frequencies.py && python3 scripts/build_doda.py`

**Rebuild icon:** `rsvg-convert` to generate the `.iconset` PNGs from `data/icon.svg`, then `iconutil -c icns data/icon.iconset -o data/icon.icns`

Run tests before touching engine.py or editor.py — 107 tests must pass.

**Next up:**
1. Status bar — save state + Arabizi mode indicator (`#42c6ff` cyan / `#ff2afc` pink dot)
2. Tabs — multiple open documents
3. Harakat/tashkil mode — vowel diacritics toggle
4. Screenshot for README — once UI is more complete, populate with a poem
5. Phase 5 — `.app` bundle via PyInstaller
