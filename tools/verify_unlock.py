#!/usr/bin/env python3
"""Check that the 'free' patch did what it should, and nothing else.

Usage: verify_unlock.py <checkout>

<checkout> is a pristine upstream clone (with its .git) that tools/unlock_pro.py has already
been run against. Everything is judged from `git diff` against upstream, so the checks hold
whatever the patch script looks like:

  1. Only the files the unlock is allowed to touch changed, and each stays small.
  2. The diff adds nothing that talks to the network, spawns processes or runs scripts.
  3. The things the unlock exists to do are actually there, and the old gates are gone.

This file is deliberately outside the set of files an automated fixer may edit, so a fix can't
loosen the check it is judged by. The appcast URL and the public key are duplicated from
tools/unlock_pro.py on purpose.
"""
import re
import subprocess
import sys
from pathlib import Path

APPCAST_PREFIX = "https://raw.githubusercontent.com/oenderg/mac-mouse-fix-free/"
SPARKLE_PUBLIC_KEY = "/t69+n8GXfMxB1YV4Xmi5E9LR5hDewXTRtwBYRAJ7SQ="

# path (regex) -> maximum added+removed lines
ALLOWED = {
    r"Mouse Fix\.xcodeproj/project\.pbxproj": 12,   # 4 settings lines, 4 added + 4 removed
    r"App/SupportFiles/App\.entitlements": 12,
    r"Helper/SupportFiles/Helper\.entitlements": 12,
    r"Shared/Constants\.h": 8,
    r"App/SupportFiles/Info\.plist": 8,
    r"App/UI/Main/Tabs/AboutTabController\.swift": 6,
    r"App/UI/Notifications/Toasts/LicenseToasts\.swift": 6,
}

# Anything in added lines that reaches outside the process. The appcast URL is the one exception.
RISKY = re.compile(
    r"URLSession|NSURLConnection|URLRequest|Process\(|NSTask|posix_spawn|execv|system\(|popen|dlopen|"
    r"NSAppleScript|osascript|/bin/|curl\b|wget\b|https?://|NSWorkspace|Keychain|SecItem",
    re.I,
)

failures = []


def fail(message):
    failures.append(message)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def main():
    root = Path(sys.argv[1]).resolve()
    if not (root / ".git").exists():
        raise SystemExit("ERROR: needs the upstream clone with its .git, to diff against")

    git(root, "add", "-N", ".")  # make new files visible to diff
    numstat = [line.split("\t") for line in git(root, "diff", "--numstat").splitlines() if line]

    changed = {}
    for added, removed, path in numstat:
        if added == "-":
            fail(f"binary file changed: {path}")
            continue
        changed[path] = int(added) + int(removed)
        limit = next((cap for pattern, cap in ALLOWED.items() if re.fullmatch(pattern, path)), None)
        if limit is None:
            fail(f"changed a file the unlock may not touch: {path}")
        elif changed[path] > limit:
            fail(f"{path}: {changed[path]} changed lines, limit is {limit}")

    for line in git(root, "diff", "-U0").splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        body = line[1:]
        if RISKY.search(body) and APPCAST_PREFIX not in body:
            fail(f"added line looks like it reaches outside the app: {body.strip()[:120]}")

    def text(rel):
        p = root / rel
        return p.read_text() if p.exists() else ""

    pbx = text("Mouse Fix.xcodeproj/project.pbxproj")
    for condition in ("IS_MAIN_APP", "IS_HELPER"):
        if f'"$(inherited) {condition} FORCE_LICENSED"' not in pbx:
            fail(f"the Xcode project does not set FORCE_LICENSED on {condition}")

    for rel in ("App/SupportFiles/App.entitlements", "Helper/SupportFiles/Helper.entitlements"):
        if "keychain-access-groups" in text(rel):
            fail(f"{rel} still asks for a keychain access group (needs a provisioning profile)")

    constants = text("Shared/Constants.h")
    if "noah-nuebling/mac-mouse-fix/update-feed" in constants:
        fail("the app would still set Sparkle's feed to upstream's feed at runtime")
    if f'@"{APPCAST_PREFIX}main"' not in constants:
        fail("Shared/Constants.h does not point Sparkle at this fork's feed")
    if f"#define kSUPublicEDKey {SPARKLE_PUBLIC_KEY}" not in constants:
        fail("Shared/Constants.h does not carry this fork's Sparkle public key")

    plist = text("App/SupportFiles/Info.plist")
    feed = re.search(r"<key>SUFeedURL</key>\s*<string>([^<]*)</string>", plist)
    if not feed or not feed.group(1).startswith(APPCAST_PREFIX):
        fail("Sparkle's feed is not this fork's appcast")
    if "noah-nuebling" in (feed.group(1) if feed else ""):
        fail("Sparkle would still update from upstream's feed")
    if SPARKLE_PUBLIC_KEY not in plist:
        fail("Info.plist does not carry this fork's Sparkle public key")

    if failures:
        print("verify_unlock: FAILED")
        for message in failures:
            print(f"  - {message}")
        sys.exit(1)
    print("verify_unlock: ok - " + ", ".join(f"{p} ({n})" for p, n in sorted(changed.items())))


if __name__ == "__main__":
    main()
