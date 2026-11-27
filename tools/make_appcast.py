#!/usr/bin/env python3
"""Generate the Sparkle appcast for a release.

Usage: make_appcast.py <archive> <version> <build-number> <download-url> <output.xml>

The EdDSA private key comes from $SPARKLE_ED_PRIVATE_KEY (a PEM). Sparkle signs the raw bytes of
the archive with ed25519 and compares against SUPublicEDKey in the app's Info.plist, so a build
signed with any other key simply won't install - which is what keeps upstream's official releases
from landing on top of this one.

`sparkle:version` is the CFBundleVersion (a number) and `sparkle:shortVersionString` the marketing
version; Sparkle compares the first and displays the second.
"""
import base64
import os
import shutil
import subprocess
import sys
import tempfile
from email.utils import formatdate
from pathlib import Path
from xml.sax.saxutils import escape

REPO = os.environ.get("REPO", "oenderg/mac-mouse-fix-free")


def openssl():
    """LibreSSL ships as /usr/bin/openssl and can't do `pkeyutl -rawin`, so find a real OpenSSL."""
    for candidate in ("/opt/homebrew/opt/openssl@3/bin/openssl",
                      "/usr/local/opt/openssl@3/bin/openssl",
                      shutil.which("openssl3") or "",
                      shutil.which("openssl") or ""):
        if candidate and Path(candidate).exists():
            version = subprocess.run([candidate, "version"], capture_output=True, text=True).stdout
            if version.startswith("OpenSSL 3") or version.startswith("OpenSSL 4"):
                return candidate
    raise SystemExit("ERROR: need OpenSSL 3+ for ed25519 signing (LibreSSL can't do -rawin)")


def sign(archive, key_pem):
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(key_pem)
        key_path = f.name
    try:
        sig = subprocess.run(
            [openssl(), "pkeyutl", "-sign", "-inkey", key_path, "-rawin", "-in", str(archive)],
            capture_output=True, check=True).stdout
    finally:
        os.unlink(key_path)
    if len(sig) != 64:
        raise SystemExit(f"ERROR: expected a 64-byte ed25519 signature, got {len(sig)}")
    return base64.b64encode(sig).decode()


def appcast(version, build_number, url, signature, length):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Mac Mouse Fix (unlocked)</title>
    <link>https://github.com/{escape(REPO)}</link>
    <description>Builds of noah-nuebling/mac-mouse-fix without the trial.</description>
    <language>en</language>
    <item>
      <title>{escape(version)} available!</title>
      <pubDate>{formatdate(localtime=False, usegmt=True)}</pubDate>
      <sparkle:version>{escape(build_number)}</sparkle:version>
      <sparkle:shortVersionString>{escape(version)}</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>10.15.0</sparkle:minimumSystemVersion>
      <sparkle:releaseNotesLink>https://github.com/{escape(REPO)}/releases/tag/v{escape(version)}-unlocked</sparkle:releaseNotesLink>
      <enclosure url="{escape(url)}"
                 sparkle:version="{escape(build_number)}"
                 sparkle:shortVersionString="{escape(version)}"
                 length="{length}"
                 type="application/octet-stream"
                 sparkle:edSignature="{escape(signature)}" />
    </item>
  </channel>
</rss>
"""


def main():
    archive, version, build_number, url, out = (Path(sys.argv[1]), sys.argv[2], sys.argv[3],
                                                 sys.argv[4], Path(sys.argv[5]))
    key_pem = os.environ.get("SPARKLE_ED_PRIVATE_KEY", "")
    if not key_pem:
        raise SystemExit("ERROR: SPARKLE_ED_PRIVATE_KEY is not set")

    signature = sign(archive, key_pem)
    document = appcast(version, build_number, url, signature, archive.stat().st_size)
    out.write_text(document)
    # The app checks the beta feed (`appcast-pre.xml`) when "check for pre-releases" is on; this
    # fork has one feed, so the beta file is the same document.
    out.with_name("appcast-pre.xml").write_text(document)
    print(f"appcast for {version} ({build_number}), edSignature {signature[:16]}...")


if __name__ == "__main__":
    main()
