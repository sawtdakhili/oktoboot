# oktoboot — اكتب

**Offline Arabic text editor with Moroccan Arabizi/Franco-Arab transliteration.**

Type phonetically in Latin characters and numbers, pick from Arabic suggestions, write in Darija and MSA. Works entirely offline. No server, no API calls.

---

## Why

Every existing option is broken:
- **Yamli** — the best transliteration engine, but online-only
- **Google Ta3reeb** — deprecated
- Everything else — either dead, crashes, or doesn't know Moroccan Darija

oktoboot is offline-first, Moroccan-first, and open source.

## Features

- **Arabizi → Arabic** as you type, with a suggestion dropdown (like Yamli)
- **Moroccan Darija first** — كيفاش، واش، بزاف، ديال directly from the DODa dictionary
- **Moroccan-specific conventions** — `ch`→ش, `j`→ج, `g`→ڭ, `9`→ق, `8`→ه, `kh`→خ
- **Numbers as letters** — `3`→ع, `7`→ح, `9`→ق in words; stay as digits when standalone
- **Persistent learning** — picks you chose are remembered permanently (unlike Yamli which forgets on close)
- **RTL text, right-aligned**, with proper BiDi for mixed Arabic/Latin text
- **Auto-save** every 30 seconds + crash recovery
- **Saves to** `.md`, `.txt`, `.org`
- **Cmd+W** to close, **Cmd+S** to save, **Cmd+±** for font size

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| Space | Accept highlighted suggestion |
| Shift+Space | Keep word as Latin |
| Enter / Tab | Accept suggestion (no space) |
| Escape | Dismiss suggestions, keep Latin |
| ↑ / ↓ | Navigate suggestions |
| Cmd+= | Bigger text |
| Cmd+- | Smaller text |
| Cmd+W | Close |
| Cmd+S | Save |

## Transliteration quick reference

| You type | Arabic |
|----------|--------|
| `3` | ع |
| `7` | ح |
| `9` | ق |
| `8` | ه |
| `2` | أ / إ / ء |
| `ch` | ش |
| `g` | ڭ |
| `j` | ج |
| `kh` | خ |
| `gh` | غ |
| `sh` | ش |

## Setup

Requires Python 3.11+ and Homebrew.

```bash
cd ~/Documents/oktoboot
python3 -m venv .venv
.venv/bin/pip install PySide6 pyobjc-framework-Cocoa
python3 scripts/build_frequencies.py   # downloads word list + Amiri font
python3 scripts/build_doda.py          # downloads Darija dictionary
```

**Run:**
```bash
PYTHONPATH=src .venv/bin/python src/oktoboot/main.py
```

## Data sources

| Data | Source | License |
|------|--------|---------|
| Moroccan Darija dictionary | [DODa](https://github.com/darija-open-dataset/dataset) | CC BY-NC 4.0 |
| Arabic word frequencies | [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords) (OpenSubtitles 2018) | CC BY-SA 3.0 |
| Amiri font | [aliftype/amiri](https://github.com/aliftype/amiri) | SIL OFL 1.1 |

See [NOTICE](NOTICE) for full attribution.

**Note:** Bundling DODa (CC BY-NC 4.0) makes this app non-commercial. The code itself is AGPL-3.0.

## License

**Code:** AGPL-3.0 — see [LICENSE](LICENSE)  
**Bundled data:** see [NOTICE](NOTICE)

Copyright © 2025 Sawt Dakhili
