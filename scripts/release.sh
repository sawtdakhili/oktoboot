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

scripts/build_app.sh
SHA=$(shasum -a 256 "$ZIP" | cut -d' ' -f1)

gh release create "v$VERSION" "$ZIP" --title "oktoboot $VERSION" --generate-notes

TAP=$(mktemp -d)
gh repo clone sawtdakhili/homebrew-tap "$TAP" -- --quiet
sed -i '' -e "s/^  version \".*\"/  version \"$VERSION\"/" \
          -e "s/^  sha256 \".*\"/  sha256 \"$SHA\"/" "$TAP/Casks/oktoboot.rb"
git -C "$TAP" commit -am "oktoboot $VERSION"
git -C "$TAP" push
rm -rf "$TAP"
echo "released $VERSION — brew upgrade picks it up"
