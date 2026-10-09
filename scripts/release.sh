#!/bin/sh
# Publish a new version: build, GitHub release, bump the Homebrew cask.
# First bump __version__ in src/oktoboot/__init__.py, commit and push.
# Needs: gh logged in, push access to sawtdakhili/homebrew-tap.
set -e
cd "$(dirname "$0")/.."
VERSION=$(PYTHONPATH=src .venv/bin/python -c "import oktoboot; print(oktoboot.__version__)")
ZIP="dist/oktoboot-$VERSION-macos-arm64.zip"

if [ -n "$(git status --porcelain)" ]; then
    echo "commit your changes first"; exit 1
fi

# Same version as a published release, but new commits: the version
# wasn't bumped. (Same commit = a rerun after a failed tap push: fine.)
if gh release view "v$VERSION" >/dev/null 2>&1; then
    TAGGED=$(git rev-list -n 1 "v$VERSION" 2>/dev/null || gh api "repos/sawtdakhili/oktoboot/commits/v$VERSION" -q .sha)
    if [ "$TAGGED" != "$(git rev-parse HEAD)" ]; then
        echo "v$VERSION is already released — bump __version__ in src/oktoboot/__init__.py first"
        exit 1
    fi
fi

# Tests first, in hidden windows (QT_QPA_PLATFORM=offscreen) so typing on
# the Mac meanwhile can't land in them. One retry each for the rare
# dropped simulated keystroke; a real failure is shown, then we stop.
for t in engine comprehensive extended darija_words editor; do
    LOG=$(mktemp)
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python "tests/test_$t.py" >"$LOG" 2>&1 ||
    QT_QPA_PLATFORM=offscreen PYTHONPATH=src .venv/bin/python "tests/test_$t.py" >"$LOG" 2>&1 ||
    { grep -E "✗|FAIL|Error" "$LOG"; echo "tests/test_$t.py fails — not releasing"; exit 1; }
    rm -f "$LOG"
done

scripts/build_app.sh
SHA=$(shasum -a 256 "$ZIP" | cut -d' ' -f1)

# Already published (a rerun after a failed tap push): don't publish again.
if gh release view "v$VERSION" >/dev/null 2>&1; then
    echo "release v$VERSION exists — updating the tap only"
    SHA=$(gh release download "v$VERSION" --pattern "*.zip" --output - | shasum -a 256 | cut -d' ' -f1)
else
    gh release create "v$VERSION" "$ZIP" --title "oktoboot $VERSION" --generate-notes
fi

TAP=$(mktemp -d)
gh repo clone sawtdakhili/homebrew-tap "$TAP" -- --quiet
sed -i '' -e "s/^  version \".*\"/  version \"$VERSION\"/" \
          -e "s/^  sha256 \".*\"/  sha256 \"$SHA\"/" "$TAP/Casks/oktoboot.rb"
if git -C "$TAP" commit -qam "oktoboot $VERSION"; then
    git -C "$TAP" push
else
    echo "tap already on $VERSION"
fi
rm -rf "$TAP"
echo "released $VERSION — brew upgrade picks it up"
