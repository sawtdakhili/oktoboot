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

## 2026-10-08 — Editor: text-damaging bugs fixed

- **Re-editing a word goes through its Latin.** Reopening a word (click, or backspace over the space after it) still leaves it untouched; Escape or moving away changes nothing. The first typed letter or backspace swaps the Arabic back to its Latin token, and from there it's a normal compose. Typed letters go at the end of the Latin, wherever the click landed. Before: backspace deleted an Arabic letter and typing put Latin inside the Arabic word.
- **Space after a re-edited word steps over an existing space** instead of adding a second one.
- **Apostrophe inside a word is a letter** (`3'`→غ, `9'`→ض, `7'`→خ, `ma'na`→معنا). At the start of a word, or at its end before a space or punctuation, it stays a quote mark (`'salam'` → `'سلام'`). Trade-off: a word can't end in an apostrophe-letter; use `3` or `2` for that.
- **Option+Backspace / Cmd+Backspace** use the normal macOS word/line delete.
- **Paste and drag-and-drop are plain text**, every pasted line is RTL, and the invisible RTL marks our own Copy adds are stripped. One Undo removes the whole paste.

## 2026-10-08 — Engine ranking rewrite (built)

Builds the "Engine ranking rules" decided above. Measured on `tests/test_darija_words.py` (126 everyday words, no learned choices): first suggestion right **70% → 87%**, right answer in the top 3 **79% → 97%**.

- **Every candidate has a cost** (`engine.py`, "Tier 2"): one cost per key used (so `kh`→خ beats `k`+`h`→كه), one per step down a key's letter list, and a cost for each short vowel written or dropped (`a`/`i`/`o`/`u` are usually written in Darija, `e` usually dropped). A final vowel is almost always written. Generation is a beam search; the old 200-candidate cap and its random `set` order are gone, so the order is the same on every run.
- **Ranking = log10(frequency + 1) − 0.8 × cost** for every candidate, so a typical-looking unknown word can beat a rare, odd-looking corpus word. The weights were tuned together on the benchmark while `test_engine.py` stayed green. Re-run both after changing any weight.
- **Doubled letters:** `mm`/`ss`/`ll`… also give one letter with shadda. It's looked up without the shadda, and listed as plain → shadda (محمد, محمّد); the literal double (مللي) ranks on its own.
- **ة only word-final** (removed from `e`'s mid-word options). **Medial أ/إ/آ** from a vowel key costs 3.0, so made-up words lose it (كنبغيك, not كأنبغيك) while real ones keep it on frequency (سأل, رأس, مسألة). A typed `2` is never penalised.
- **Darija verb prefixes** `kan`/`kay`/`kat` at the start of a word → كن/كي/كت (كنبغي, كيخدم).
- **Overrides added** for bad DODa entries: `nhar` (DODa gave يوم, a translation), `had` (هادا), `drari` (الدراري), plus `chhal` → شحال.
- The benchmark fails below 85% first-suggestion accuracy (`MIN_TOP1`). Raise the floor as the engine improves.
- Editor tests 7, 8 and 25 now pick suggestions by content, not list position, so ranking changes don't break them.

`chokran` question decided by Saad, see the next entry.

## 2026-10-08 — Final "an" can be tanwin

Saad: `chokran` → شكراً, then شكرا, then شكران ("the an at the end should be a tanwin"). This reverses the July override that put شكران first.
- **General rule** (`_generative_lookup`): a word ending in `an` also gets the ـاً (tanwin) spelling and the plain ـا spelling, built from the word minus its `n`. They cost `_TANWIN_COST` = 2.0 (+0.5 for the plain one), and the word list stores the tanwin forms, so frequency decides: جداً, أيضاً, مثلاً come first, while names keep their ن (رمضان, سلمان, إنسان, سلطان, زمان).
- `chokran` itself has an override in exactly Saad's order. `an` is not always tanwin: of 20 Darija `-an` words checked, only `nadman` came out wrong (نادماً first), so it has an override → ندمان. Unrelated misses seen in the same check: `lmizan` → لماذا, `3yan` → عين. Benchmark after: 88% first, 98% top 3.
- The word list `tests/test_darija_words.py` was accepted by Saad as the benchmark.

## 2026-10-09 — Packaging: PyInstaller, Apple Silicon, macOS 15+

- **PyInstaller** (most used, actively maintained, good Qt support) over py2app or Briefcase. The recipe is `oktoboot.spec`; `scripts/build_app.sh` builds the app, runs `--selftest` inside it, and makes `dist/oktoboot-<version>-macos-arm64.zip`.
- **Apple Silicon only** (Saad). **macOS 15+:** the Homebrew Python and the PySide6 wheels inside are built for 15.0, so the app can't honestly claim older. Lowering it would need a python.org Python and older PySide6 wheels; not worth it now.
- Bundle ID `com.oktoboot.oktoboot`, version 0.1.0, ad-hoc signed (no paid Apple account), so users click "Open Anyway" once (README).
- Unused Qt parts are filtered out (virtual-keyboard and PDF plugins, and the QML/Quick/PDF/Network frameworks they pull in): app 148 → 128 MB, zip 47 MB.
- `oktoboot --selftest` checks the bundled data loads and the engine answers, without a window.
- Checked: valid signature; first launch with an empty home folder works; a quarantined (downloaded) copy is rejected by Gatekeeper as expected. **Not yet checked by a human:** the real "Open Anyway" click-through, and typing in the packaged app.
- NOTICE now also credits Qt/PySide6 (LGPL-3.0), Python (PSF) and PyObjC (MIT), which are all inside the app.

## 2026-10-09 — Release v0.1.0 + own Homebrew tap

- Saad uses brew first, so the cask lives in his own public tap `sawtdakhili/homebrew-tap` (no Homebrew review, updates land as soon as they're pushed). Install: `brew install --cask sawtdakhili/tap/oktoboot`.
- `scripts/release.sh` does a whole update: build, GitHub release, bump `version`/`sha256` in the cask.
- Ad-hoc signing changes with every build, so macOS likely asks for "Open Anyway" again after each update. Only a paid Apple developer account ($99/yr) avoids it; not now.
- The cask's `zap` removes `~/Library/Application Support/oktoboot` (learned words + recovery file) only on `brew uninstall --zap`.

## 2026-10-09 — First-use fixes + ideas taken from Yamli

From Saad's first test of the brew install:
- **Blank lines:** Qt's Enter on an empty paragraph that carries a block format (ours are all RTL) only clears the format. The editor now inserts the paragraph itself.
- **Clicking a suggestion** took focus from the editor, so the word was committed as Latin and the click lost. The popup can't take focus now.
- **آ:** word-initial `aa` → آ (aakhir → آخر, aamin → آمين); `2aa` → آ anywhere (9or2aan → قرآن). Mid-word `aa` stays ا.
- **Live preview (Saad):** Up/Down puts the highlighted suggestion in the text itself. Typing or Backspace goes back to the Latin; Escape puts the Latin back (or the original word, in a re-edit).
- **Leaving a word keeps its suggestion (Saad agreed, "we'll see"):** arrows, a click elsewhere, a Cmd shortcut or focus moving inside the app now commit the highlighted suggestion, as Space does. Before, the word silently stayed Latin. Escape (popup closed) and Shift+Space still keep the Latin. Revert = `_finish_word` back to `_commit_latin`.

Yamli study (its own API, 157 words: oktoboot 85% first-right, Yamli 74%; was 82%). Taken from Yamli:
- Darija article: bare `l` before a consonant → ال (lmaghrib → المغرب); the ل-only form stays in the list.
- A word never starts with ي/و for a vowel: initial i/e/o/u → إ/ا/أ (inchallah → إنشالله, ekhtar → اختار). `allah` → الله as one piece.
- `_NAMES`: ~65 common Moroccan names with their Latin spellings, only ones the rules got wrong. Names win over same-spelled words (walid → وليد before والد).
Kept different from Yamli on purpose: Moroccan alif spellings, ڭ, full list visible, Enter accepts, Tab inserts a tab, mode shown by cursor colour. Not taken: "show more" short list, report-a-word, hyphenated words.

## 2026-10-09 — /yousure on the 0.1.1 build, and a letter check

Applied (Saad: "okay for all fixes"):
- Leaving a word converts it but **doesn't teach the ranking** (`_finish_word` → `learn=False`). Otherwise every arrow/click-away saved the top suggestion as Saad's choice, and learned choices outrank everything.
- **Cmd+Z / Shift+Cmd+Z mid-word** keep the Latin (no conversion first). Converting first made the undo revert the conversion and left a wrong learned choice.
- `scripts/release.sh` runs the 5 test suites first (one retry each, for the keystroke flakes) and can be rerun after a failed tap push (skips an existing release, takes the published zip's sha).
- Open: Saad's report "delete the space → suggestions should reappear and keep changing" — not reproduced in simulation (bare editor or full window, keyboard or mouse pick). Only the mouse-click bug was found and fixed. Needs his exact key sequence if it recurs.
- Open: a human check of 0.1.1 (Open Anyway + typing) — DECISIONS 2026-10-09 packaging still says not done.
- Saad: **no shortcut converts a word** (Cmd/Ctrl/Option + key mid-word → the Latin stays). Finish-on-leave is now arrows, clicks and in-app focus loss only.

Letter check against DODa (7,325 one-word Moroccan pairs; "North Africa + Arabizi first", Saad):
- `z` = ز. ذ/ظ kept but cost +3 (`_RARE_LETTER_COST`); ذنب no longer shows right under زينب.
- `x` = ش first (Maghreb texting: wax → واش, kifax → كيفاش), then كس for loanwords; an x-word with no entry is looked up with ch (xhal → شحال). `taxi` override.
- Hamza `2` takes its seat from the vowels around it (ra2is → رئيس, su2al → سؤال, sma2 → سماء, 2ila → إلى).
- Measured but **not changed**: final ة vs ا (lowering ة's cost gained <1 point on non-dictionary words; dictionary words already right), emphatics ط/ض/ص (truly ambiguous; frequency decides), g → ڭ vs ق/ج (frequency decides; DODa uses ڭ by convention, typing practice varies).
