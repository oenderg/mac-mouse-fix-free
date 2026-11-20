#!/usr/bin/env bash
# Build Mac Mouse Fix from an already-unlocked checkout.
# Usage: build.sh <checkout-dir> <version> [output-dir]
#
# Builds ad-hoc, then re-signs with $SIGN_IDENTITY when set (plus $SIGN_KEYCHAIN if the identity
# lives outside the default search list). The identity matters: an ad-hoc signature makes the
# designated requirement a cdhash, so macOS treats every build as a different app and drops its
# Accessibility grant. A certificate makes it `identifier and certificate leaf`, which is stable
# across builds.
#
# Re-signing after the fact rather than handing the identity to Xcode is deliberate: Xcode only
# selects identities that pass a trust evaluation, and a self-signed cert never will. It silently
# falls back to ad-hoc instead of failing, which is the worst of both worlds.
#
# The project is built with `CODE_SIGN_ENTITLEMENTS` intact but with the keychain-access-groups
# entitlement removed by tools/unlock_pro.py: that is the one entitlement Xcode insists needs a
# provisioning profile, and a self-signed build has none.
set -euo pipefail

SRC="$(cd "$1" && pwd)"
VERSION="$2"
OUT="$(mkdir -p "${3:-$PWD/dist}" && cd "${3:-$PWD/dist}" && pwd)"

# A high, monotonically increasing CFBundleVersion, so Sparkle (and its custom comparator in
# App/Update/CoolSUComparator.m, which uses the build number to disambiguate equal versions)
# always sees a newer build across upstream versions. 3.1.0 -> 3001000.
BUILD_NUMBER="$(printf '%s' "$VERSION" | awk -F. '{printf "%d", $1*1000000 + $2*1000 + $3}')"
[ -n "$BUILD_NUMBER" ] || { echo "cannot derive a build number from '$VERSION'" >&2; exit 1; }

cd "$SRC"
xcodebuild -project "Mouse Fix.xcodeproj" -scheme App -configuration Release \
  -derivedDataPath DerivedData \
  ARCHS="arm64 x86_64" ONLY_ACTIVE_ARCH=NO \
  CODE_SIGN_IDENTITY=- CODE_SIGN_STYLE=Manual DEVELOPMENT_TEAM= \
  ENABLE_HARDENED_RUNTIME=NO PROVISIONING_PROFILE_SPECIFIER= \
  build

APP="$SRC/DerivedData/Build/Products/Release/Mac Mouse Fix.app"
HELPER="$APP/Contents/Library/LoginItems/Mac Mouse Fix Helper.app"
[ -d "$APP" ] || { echo "no app at $APP" >&2; exit 1; }
[ -d "$HELPER" ] || { echo "the helper was not embedded at $HELPER" >&2; exit 1; }

# Stamp the version ourselves. The app's own build phase increments CFBundleVersion in the
# source tree, but we want it predictable and shared with the appcast; the helper usually
# mirrors the app (a build phase copies it), and `helperIsActive` compares the two. The helper
# target has no MARKETING_VERSION of its own, so its CFBundleShortVersionString can be missing
# from the built plist - hence the Add fallback.
set_plist_key() {
  /usr/libexec/PlistBuddy -c "Set :$2 $3" "$1" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :$2 string $3" "$1"
}
for plist in "$APP/Contents/Info.plist" "$HELPER/Contents/Info.plist"; do
  set_plist_key "$plist" CFBundleShortVersionString "$VERSION"
  set_plist_key "$plist" CFBundleVersion "$BUILD_NUMBER"
done

# Sign nested code first (deepest paths first), then the app itself. --deep alone misses the
# embedded helper, Sparkle's Autoupdate.app and the swift dylibs on newer toolchains. The app
# keeps the entitlements Xcode embedded. We always sign - even without a certificate, ad-hoc -
# because stamping the version above invalidated the signature the build produced.
IDENTITY="${SIGN_IDENTITY:--}"
sign() { codesign --force --sign "$IDENTITY" ${SIGN_KEYCHAIN:+--keychain "$SIGN_KEYCHAIN"} "$@"; }
while IFS= read -r -d '' nested; do
  sign --preserve-metadata=entitlements,flags "$nested"
done < <(find "$APP/Contents" \( -name '*.xpc' -o -name '*.app' -o -name '*.framework' -o -name '*.dylib' \) -print0 | sort -z -r)
# launchd signs the embedded agent plist (CodeSignOnCopy in the project), so it must carry our
# identity too or launchd may refuse to load the job.
while IFS= read -r -d '' agent; do
  sign "$agent"
done < <(find "$APP/Contents/Library/LaunchAgents" -name '*.plist' -print0 2>/dev/null)
sign --preserve-metadata=entitlements,flags "$APP"

if [ -n "${SIGN_IDENTITY:-}" ]; then
  authority=$(codesign -dv --verbose=2 "$APP" 2>&1 | sed -n 's/^Authority=//p')
  [ -n "$authority" ] || { echo "asked to sign as '$SIGN_IDENTITY' but the app is still ad-hoc" >&2; exit 1; }
  echo "signed by: $authority"
else
  echo "signed by: ad-hoc"
fi

codesign --verify --deep --strict "$APP"
test "$(defaults read "$APP/Contents/Info.plist" CFBundleShortVersionString)" = "$VERSION"
test "$(defaults read "$APP/Contents/Info.plist" CFBundleVersion)" = "$BUILD_NUMBER"
codesign -d -r- "$APP" 2>&1 | sed -n 's/^#* *designated => /designated requirement: /p'
echo "architectures: $(lipo -archs "$APP/Contents/MacOS/Mac Mouse Fix")"
echo "build number: $BUILD_NUMBER"

# A zip with the app at the root, exactly like upstream's MacMouseFixApp.zip: that is the layout
# Sparkle 1 unarchives. `--keepParent` puts `Mac Mouse Fix.app` at the top of the archive.
ZIP="$OUT/MacMouseFixApp-$VERSION-unlocked.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
echo "built $ZIP"
