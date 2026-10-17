#!/usr/bin/env bash
# Install the latest unlocked Mac Mouse Fix build.
#
#   curl -fsSL https://raw.githubusercontent.com/oenderg/mac-mouse-fix-free/main/tools/install.sh | bash
#
# No sudo: /Applications is writable by admin users and tccutil works on your own TCC database.
# If anything here asks you for a password, something is wrong - stop and read the script.
set -euo pipefail

REPO="${REPO:-oenderg/mac-mouse-fix-free}"
APP="/Applications/Mac Mouse Fix.app"
BUNDLE_ID="com.nuebling.mac-mouse-fix"
HELPER_ID="com.nuebling.mac-mouse-fix.helper"
BACKUPS="$HOME/Library/Application Support/MacMouseFix-backups"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say() { printf '\033[1m==>\033[0m %s\n' "$1"; }
fail() { printf '\033[31merror:\033[0m %s\n' "$1" >&2; exit 1; }

[ "$(uname -s)" = "Darwin" ] || fail "macOS only"
[ "$(sw_vers -productVersion | cut -d. -f1)" -ge 11 ] || fail "needs macOS 11 or newer"
[ -w /Applications ] || fail "/Applications isn't writable by your user - you need an admin account"

say "Finding the latest release"
assets=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | sed -n 's/.*"browser_download_url": *"\([^"]*\)".*/\1/p')
url=$(printf '%s\n' "$assets" | grep -E '\.zip$' | head -1 || true)
[ -n "$url" ] || fail "no release asset found for $REPO"
version=$(basename "$url" | sed -E 's/^MacMouseFixApp-(.*)-unlocked\.zip$/\1/')
say "Downloading Mac Mouse Fix $version"
curl -fsSL "$url" -o "$TMP/download"
mkdir -p "$TMP/extracted"
ditto -x -k "$TMP/download" "$TMP/extracted"
new="$TMP/extracted/Mac Mouse Fix.app"
[ -d "$new" ] || fail "the downloaded archive didn't contain Mac Mouse Fix.app"

codesign --verify --deep --strict "$new" || fail "downloaded app failed signature verification"
new_req=$(codesign -d -r- "$new" 2>&1 | sed -n 's/^designated => //p')
say "Signed as: ${new_req:-unknown}"

old_req=""
if [ -d "$APP" ]; then
  old_req=$(codesign -d -r- "$APP" 2>&1 | sed -n 's/^designated => //p' || true)
  old_version=$(defaults read "$APP/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null || echo unknown)
  mkdir -p "$BACKUPS"
  say "Backing up the installed Mac Mouse Fix $old_version"
  rm -rf "$BACKUPS/MacMouseFix-$old_version.app"
  ditto "$APP" "$BACKUPS/MacMouseFix-$old_version.app"
fi

osascript -e 'quit app "Mac Mouse Fix"' >/dev/null 2>&1 || true
sleep 2
pkill -f "$APP/Contents/MacOS/Mac Mouse Fix" 2>/dev/null || true
pkill -f "Mac Mouse Fix Helper" 2>/dev/null || true

say "Installing to $APP"
rm -rf "$APP"
ditto "$new" "$APP"
# curl doesn't set com.apple.quarantine, but a re-run over a browser-downloaded copy might have.
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

# macOS binds a permission grant to the bundle ID *and* the code signature. Resetting when the
# signature is unchanged would needlessly throw away a working grant, so only do it when the
# identity actually differs - e.g. coming from upstream's or your own Apple-signed build.
needs_grant=0
if [ -z "$old_req" ]; then
  needs_grant=1
elif [ "$old_req" != "$new_req" ]; then
  say "Signing identity changed - resetting permissions so the new grant can bind"
  tccutil reset Accessibility "$HELPER_ID" >/dev/null 2>&1 || true
  tccutil reset Accessibility "$BUNDLE_ID" >/dev/null 2>&1 || true
  needs_grant=1
else
  say "Same signing identity - your Accessibility grant carries over"
fi

say "Launching Mac Mouse Fix $version"
open "$APP"

if [ "$needs_grant" = "1" ]; then
  cat <<'EOF'

One thing left: Mac Mouse Fix needs to control the mouse, so it needs Accessibility.

  System Settings > Privacy & Security > Accessibility  ->  enable "Mac Mouse Fix Helper"

Opening that pane now. The app walks you through the rest on first launch.
EOF
  open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
fi

say "Done. Backups of previous versions live in $BACKUPS"
