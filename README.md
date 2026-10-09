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
- **Persistent learning** — every choice (Arabic or "keep as Latin") is remembered permanently and ranks accordingly next time (unlike Yamli which forgets on close)
- **Arabizi on/off toggle** — Shift+Tab switches to plain Latin typing (URLs, emails, English) without fighting suggestions word by word
- **RTL text, right-aligned**, with proper BiDi for mixed Arabic/Latin text
- **Auto-save** every 30 seconds + crash recovery
- **Saves to** `.md`, `.txt`, `.org`
- **Cmd+W** to close, **Cmd+S** to save, **Cmd+±** for font size
- **Font family picker** (Format menu) — Amiri or Geeza Pro; both are the only bundled/system options that cover the full Darija letter set (ڭ included)

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| Space | Accept highlighted suggestion |
| Shift+Space | Keep word as Latin (this choice is remembered, and ranks higher next time) |
| Shift+Tab | Toggle Arabizi mode on/off |
| Enter / Tab | Accept suggestion (no space) |
| Escape | Dismiss suggestions, keep Latin |
| ↑ / ↓ | Navigate suggestions |
| Click a committed word | Re-open it for editing |
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

## Install

Requires a Mac with Apple Silicon (M1 or newer) and macOS 15 (Sequoia) or newer.

**Download:** get `oktoboot-<version>-macos-arm64.zip` from [Releases](https://github.com/sawtdakhili/oktoboot/releases), unzip it, and drag `oktoboot.app` to Applications.

**Homebrew:**
```bash
brew install --cask sawtdakhili/tap/oktoboot
```

**First launch:** oktoboot isn't signed with a paid Apple developer account, so macOS blocks it the first time (and usually again after an update).
1. Open oktoboot. macOS says it can't verify the app. Click **Done**.
2. Open **System Settings → Privacy & Security**, scroll down, and click **Open Anyway** next to the oktoboot message.
3. Confirm with your password or Touch ID. From then on it opens normally.

(Right-click → Open no longer skips this step on macOS 15 and later.)

## Run from source

Requires Python 3.11+ and Homebrew.

```bash
git clone https://github.com/sawtdakhili/oktoboot.git && cd oktoboot
python3 -m venv .venv
.venv/bin/pip install PySide6 pyobjc-framework-Cocoa
python3 scripts/build_frequencies.py   # downloads word list + Amiri font
python3 scripts/build_doda.py          # downloads Darija dictionary (needs the gh CLI, logged in)
```

**Run:**
```bash
PYTHONPATH=src .venv/bin/python src/oktoboot/main.py
```

**Build the app:** `.venv/bin/pip install pyinstaller`, then `scripts/build_app.sh` → `dist/oktoboot.app` and the release zip.

## Data sources

| Data | Source | License |
|------|--------|---------|
| Moroccan Darija dictionary | [DODa](https://github.com/darija-open-dataset/dataset) | CC BY-NC 4.0 |
| Arabic word frequencies | [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords) (OpenSubtitles 2018) | CC BY-SA 3.0 |
| Amiri font | [aliftype/amiri](https://github.com/aliftype/amiri) | SIL OFL 1.1 |
| Qt / PySide6 (in the app) | [Qt for Python](https://www.qt.io/qt-for-python) | LGPL-3.0 |
| Python (in the app) | [python.org](https://www.python.org) | PSF License |
| App icon | Original work | © 2026 Sawt Dakhili |

See [NOTICE](NOTICE) for full attribution.

**Note:** Bundling DODa (CC BY-NC 4.0) makes this app non-commercial. The code itself is AGPL-3.0.

## License

**Code:** AGPL-3.0 — see [LICENSE](LICENSE)  
**Bundled data:** see [NOTICE](NOTICE)

Copyright © 2026 Sawt Dakhili
