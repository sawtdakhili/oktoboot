# DECISIONS — oktoboot

Append-only record of decisions and reversals (design philosophy rule 4, `homelab/CLAUDE.md`).
Newest at the bottom. Dates are ISO 8601.

## 2026-10-08 — Ship before tabs and harakat

First public release comes before tabs and the harakat mode. Order to get there:
1. fix the editor bugs that damage text (backspace/click re-edit, paste keeping rich formatting, apostrophe keys, Option+Backspace),
2. engine quality fixes (below),
3. safe saving,
4. package as a `.app`,
5. release on GitHub.

## 2026-10-08 — Engine ranking rules (decided, not yet built)

- **Deterministic order.** The same input always gives the same suggestion order, on every launch. (Today, unknown words come out of a Python `set`, so their order changes per launch.)
- **Unknown words ranked by mapping order, not length.** Reverses the current "longest first" sort for words not found in the word list. Longest-first rewarded letter-by-letter junk and split digraphs (`kh` → كه instead of خ).
- **Doubled Latin letters give both options.** `mm`/`ss`/`ll` also yield a single letter. Order: plain single (محمد), then the shadda version (محمّد), then the literal double (مممد) when it's a real word. The word-list lookup uses the form without shadda. When the harakat mode exists, the shadda version becomes the default.
- **ة only at the end of a word.**
- **أ in the middle of a word only when** the user typed `2` (`sa2al` → سأل), or the result is a real word in the frequency list (رأس). This is not a blanket ban: real words like سأل, رأس, مسألة keep their أ.
- **Measuring progress:** a list of about 100 everyday Darija words with their expected spellings, always run with `learned_db=None`. The user's own learned choices outrank the engine and would hide or fake engine changes.

## 2026-10-08 — Frequency DB rebuilt as WITHOUT ROWID; rare words kept

The table is now `WITHOUT ROWID` with no extra `idx_word` index: 180 MB → 51 MB. All 2,507,189 words were kept, and the scores were checked identical on 40 test words. Pruning rare words was rejected: the 180 MB was mostly the same index stored twice, and the أ rule above needs "is it in the word list" to decide what a real word is.

## 2026-10-08 — Data sources pinned to exact commits

`scripts/build_frequencies.py` (FrequencyWords `525f9b5`, Amiri `6331fc8`) and `scripts/build_doda.py` (DODa `f4dd400`, the commit that was current when `doda.db` was first built) no longer pull the latest branch. To update a source, bump the commit here with the reason.

## 2026-10-08 — Saving: temp file + swap, `.bak` once per session

`MainWindow._write` writes to a hidden temp file, then swaps it in with `os.replace`, so a crash mid-save can't empty the file. `.bak` now holds the file as it was before this session's first save, written once per file per session. Before this, `.bak` was rewritten on every save with the same content as the file, so it never held an older version.

## 2026-10-08 — /yousure premortem on the ship plan: applied / skipped

Applied: 1 (frequency DB slimmed, pruning dropped), 2 (safe saving), 3 (`pyproject.toml` build line `setuptools.build_meta` + pyobjc dependency; `DATA_DIR` falls back to `sys._MEIPASS` when bundled), 5 (this file, data pins, the no-learned-DB testing rule).
Decided: 4 — see "Distribution" below.
Not done yet from the review: checking the release's license credits (Amiri OFL, FrequencyWords CC BY-SA, DODa CC BY-NC) in the packaged app, and checking re-edit fixes against real app switching, not QTest alone. Both belong to the bug-fix and packaging steps.

## 2026-10-08 — Distribution: unsigned `.app` on GitHub + own Homebrew tap

Saad doesn't mind macOS's "Open Anyway" step, so there's no paid Apple Developer ID.
- **GitHub Releases:** an unsigned, zipped `oktoboot.app`. The README gives the real first-launch steps: open once → System Settings → Privacy & Security → Open Anyway. Right-click → Open no longer works for this on macOS 15+.
- **Own Homebrew tap** (`sawtdakhili/homebrew-tap`, installed with `brew install --cask sawtdakhili/tap/oktoboot`): a cask that downloads that same release zip. It does not strip the quarantine flag, so users get the same "Open Anyway" step. The main Homebrew catalogue isn't possible: since 2026-09-01 it disables casks that fail Gatekeeper.
- Rejected: a tap formula that builds the app on the user's Mac. It avoids the block, but installs are slow and it's an extra build recipe to maintain (rule 1).
