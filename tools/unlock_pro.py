#!/usr/bin/env python3
"""Re-appliable 'free' patch for a pristine noah-nuebling/mac-mouse-fix checkout.

Anchors on Swift declarations, build settings and literal call sites rather than line
numbers, so it survives most upstream churn. A missing required anchor is a hard failure:
better a red build than a silently locked one.

What it changes, and why:
  1. Defines the `FORCE_LICENSED` Swift compilation condition on the app and the helper.
     It is upstream's own flag ("Makes the app accept any license key", see the comment atop
     Shared/License/License.swift): `GetLicenseState.get()` then returns a licensed state via
     `licenseStateFromOverrides()`, so the 30-day trial never expires and the helper never
     locks itself down. No license key and no network call to Gumroad are involved. The flag
     has to be added to both targets, because they each compile the licensing code.
  2. Drops the `keychain-access-groups` entitlement from the app and the helper. It is the
     only entitlement that needs a provisioning profile, and a self-signed certificate has
     none, so Xcode refuses to build the project ad-hoc without this. The app and the helper
     then fall back to their own default keychain group, which is fine because the unlock no
     longer reads the license key or the trial counter from the shared item.
  3. Points Sparkle at this fork's appcast and public key (in Shared/Constants.h, which is
     what sets the feed at runtime, and in Info.plist, the fallback), so the app can't replace
     itself with the official, locked build.
  4. Rewords the two places that say "FORCE_LICENSED" in the UI, so the About tab and the
     license toast read like a product, not like a build flag.

Usage: unlock_pro.py <path-to-mac-mouse-fix-checkout>
"""
import re
import sys
from pathlib import Path

applied, skipped = [], []

# Public by design: the appcast this fork's CI publishes and the public half of the EdDSA key
# it signs it with. Sparkle rejects any update whose signature doesn't verify against this key.
# Checked in CI by tools/verify_unlock.py against every upstream release.
#
# These two are duplicated in tools/verify_unlock.py on purpose: that file is outside what an
# automated fixer may edit, so it must not import anything that a fix could change.
REPO = "oenderg/mac-mouse-fix-free"
FEED_BASE = f"https://raw.githubusercontent.com/{REPO}/main"
APPCAST_URL = f"{FEED_BASE}/appcast.xml"
SPARKLE_PUBLIC_KEY = "/t69+n8GXfMxB1YV4Xmi5E9LR5hDewXTRtwBYRAJ7SQ="

UPSTREAM_FEED_BASE = "https://raw.githubusercontent.com/noah-nuebling/mac-mouse-fix/update-feed"
LOOKS_LIKE_UPSTREAM_KEY = r"^(#define\s+kSUPublicEDKey\s+)\S+[ \t]*$"

ABOUT_FORCE_MESSAGE_OLD = '"The app will appear to be licensed due to the FORCE_LICENSED flag"'
ABOUT_FORCE_MESSAGE_NEW = '"This is an unlocked build: licensed without a license key"'
TOAST_FORCE_MESSAGE_OLD = '"FORCE_LICENSED flag is active"'
TOAST_FORCE_MESSAGE_NEW = '"This is an unlocked build of Mac Mouse Fix"'


def record(label, required, reason):
    if required:
        raise SystemExit(f"ERROR: unlock patch anchor drifted - {label}: {reason}")
    skipped.append(f"{label} ({reason})")


def replace_literal(path, old, new, label, required=True, count=1):
    s = path.read_text()
    if old not in s:
        record(label, required, f"not found in {path.name}: {old!r}")
        return 0
    n = s.count(old)
    path.write_text(s.replace(old, new) if count == 0 else s.replace(old, new, count))
    applied.append(label)
    return n


def patch_force_licensed(root):
    pbx = root / "Mouse Fix.xcodeproj/project.pbxproj"
    # One setting per target configuration (Debug and Release), for both targets. Replace them
    # all; a missing one is fatal so the unlock can't silently half-apply.
    for condition in ("IS_MAIN_APP", "IS_HELPER"):
        old = f'"$(inherited) {condition}"'
        new = f'"$(inherited) {condition} FORCE_LICENSED"'
        n = replace_literal(pbx, old, new, f"FORCE_LICENSED on {condition}", count=0)
        if n == 0:
            raise SystemExit(f"ERROR: no SWIFT_ACTIVE_COMPILATION_CONDITIONS for {condition} in the Xcode project")
        applied[-1] = f"{applied[-1]} ({n} configs)"


def patch_entitlements(root):
    # The value is `$(AppIdentifierPrefix)com.nuebling.mac-mouse-fix.keychain-group` upstream; the
    # regex only anchors on the key, so a rename of the group is fine too.
    pattern = re.compile(
        r"[ \t]*<key>keychain-access-groups</key>\s*<array>.*?</array>\s*\n",
        re.S,
    )
    for rel in ("App/SupportFiles/App.entitlements", "Helper/SupportFiles/Helper.entitlements"):
        path = root / rel
        s = path.read_text()
        patched, n = pattern.subn("", s, count=1)
        if n == 0:
            record(f"no provisioning profile needed ({rel})", True,
                   "no keychain-access-groups block")
            continue
        path.write_text(patched)
        applied.append(f"no provisioning profile needed ({rel})")


def patch_sparkle(root):
    constants = root / "Shared/Constants.h"
    replace_literal(constants, UPSTREAM_FEED_BASE, FEED_BASE, "Sparkle feed base (Constants.h)")
    s = constants.read_text()
    patched, n = re.subn(LOOKS_LIKE_UPSTREAM_KEY,
                         rf"\g<1>{SPARKLE_PUBLIC_KEY}",
                         s, count=1, flags=re.M)
    if n == 0:
        record("Sparkle public key (Constants.h)", True, "no kSUPublicEDKey define")
    else:
        constants.write_text(patched)
        applied.append("Sparkle public key (Constants.h)")

    plist = root / "App/SupportFiles/Info.plist"
    s = plist.read_text()
    for key, value, label in (("SUFeedURL", APPCAST_URL, "Sparkle feed URL (Info.plist)"),
                              ("SUPublicEDKey", SPARKLE_PUBLIC_KEY, "Sparkle public key (Info.plist)")):
        patched, n = re.subn(rf"(<key>{key}</key>\s*<string>)[^<]*(</string>)",
                             lambda m: m.group(1) + value + m.group(2), s)
        if n == 0:
            record(label, True, "no entry")
        else:
            s = patched
            applied.append(label)
    plist.write_text(s)


def patch_ui_text(root):
    about = root / "App/UI/Main/Tabs/AboutTabController.swift"
    replace_literal(about, ABOUT_FORCE_MESSAGE_OLD, ABOUT_FORCE_MESSAGE_NEW,
                    "About tab wording", required=False)
    toast = root / "App/UI/Notifications/Toasts/LicenseToasts.swift"
    replace_literal(toast, TOAST_FORCE_MESSAGE_OLD, TOAST_FORCE_MESSAGE_NEW,
                    "license toast wording", required=False)


def patch_license_ui_check(root):
    """Fail loudly if upstream starts defining FORCE_LICENSED semantics somewhere new."""
    gs = (root / "Shared/License/Retrieve/GetLicenseState.swift")
    if gs.exists() and "FORCE_LICENSED" not in gs.read_text():
        record("FORCE_LICENSED still exists in GetLicenseState.swift", True,
               "the flag is gone from the licensing code")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not (root / "Mouse Fix.xcodeproj/project.pbxproj").exists() or not (root / "App").exists():
        raise SystemExit(f"ERROR: {root} does not look like a Mac Mouse Fix checkout")
    patch_license_ui_check(root)
    patch_force_licensed(root)
    patch_entitlements(root)
    patch_sparkle(root)
    patch_ui_text(root)
    print(f"unlocked {root}")
    for label in applied:
        print(f"  applied: {label}")
    for label in skipped:
        print(f"  skipped: {label}")


if __name__ == "__main__":
    main()
