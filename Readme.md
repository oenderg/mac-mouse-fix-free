<h1><img src="tools/assets/icon-free.png" width="72" align="absmiddle">&nbsp;mac-mouse-fix-free</h1>

**[Mac Mouse Fix](https://github.com/noah-nuebling/mac-mouse-fix) with the 30-day trial removed.** An unofficial macOS build of the mouse driver, rebuilt automatically from every upstream release, signed, with working auto-updates.

> Not affiliated with or endorsed by Noah Nuebling. If Mac Mouse Fix is useful to you, he sells it for a few bucks at [macmousefix.com](https://macmousefix.com/), and that is what pays for the project.

## Install

Requires macOS 11 or newer. Universal binary, Apple Silicon and Intel.

```bash
curl -fsSL https://raw.githubusercontent.com/oenderg/mac-mouse-fix-free/main/tools/install.sh | bash
```

It downloads the [latest release](https://github.com/oenderg/mac-mouse-fix-free/releases/latest), verifies the signature, backs up whatever Mac Mouse Fix you already have into `~/Library/Application Support/MacMouseFix-backups/`, installs, and launches. No `sudo`, and it doesn't want your password. If a `curl | bash` one-liner ever asks for one, that's your cue to read it first: [this one is short](tools/install.sh).

Then grant **Accessibility** in System Settings → Privacy & Security, which the app needs to remap your mouse. The installer opens the right pane for you. Your existing settings carry over (same bundle ID).

<details>
<summary><b>Manual install</b>, if you'd rather not pipe a script into bash</summary>

```bash
# download MacMouseFixApp-<version>-unlocked.zip from the releases page and unzip it, then:
osascript -e 'quit app "Mac Mouse Fix"'
ditto "/Applications/Mac Mouse Fix.app" ~/Desktop/MacMouseFix-backup.app   # if you have one already
rm -rf "/Applications/Mac Mouse Fix.app"
ditto "/path/to/unzipped/Mac Mouse Fix.app" "/Applications/Mac Mouse Fix.app"
xattr -dr com.apple.quarantine "/Applications/Mac Mouse Fix.app"
tccutil reset Accessibility com.nuebling.mac-mouse-fix.helper
open "/Applications/Mac Mouse Fix.app"
```

The `xattr` line matters when you download through a browser: browsers tag downloads with `com.apple.quarantine`, and these builds aren't notarized, so Gatekeeper blocks the first launch. The installer script sidesteps this by downloading with `curl`. The `tccutil` line clears the permission entry belonging to your previous copy, because macOS binds a grant to the bundle ID *and* the code signature.

</details>

<details>
<summary><b>What's different from upstream</b></summary>

| | Upstream 3.x | mac-mouse-fix-free |
|---|---|---|
| After 30 days | asks for a license key, the helper stops until you buy | fully licensed, no key, no countdown |
| About tab | trial counter, then a thank-you | "This is an unlocked build" |
| License key | used | not needed (and not read: see below) |
| Auto-update | upstream's feed | this repo's feed, signed with this repo's key |
| Everything else | | upstream's code, unmodified |

The unlock is upstream's own `FORCE_LICENSED` compilation flag, defined on the app and the helper. With it, `GetLicenseState.get()` returns a licensed state through `licenseStateFromOverrides()`, so nothing counts the trial down and the helper never locks itself. There are no fake responses to Gumroad and no network call is needed to stay licensed.

Two smaller changes come with it: the `keychain-access-groups` entitlement is dropped (the one entitlement that needs a provisioning profile, which a self-signed build doesn't have), and Sparkle is pointed at this repo. Dropping the keychain group means the app keeps its own keychain item: a license key from a previous, official copy is not read — which is fine, because it is not needed. The "Buy Mac Mouse Fix" button and the license window are still upstream's and still work.

</details>

<details>
<summary><b>How it works</b></summary>

The patch is a script, not a fork's worth of diverging commits. [`tools/unlock_pro.py`](tools/unlock_pro.py) runs against a pristine upstream release tag and does four things:

1. Defines `FORCE_LICENSED` on the app and helper targets in the Xcode project.
2. Drops the `keychain-access-groups` entitlement from the app and the helper.
3. Repoints Sparkle's feed (in `Shared/Constants.h`, which sets it at runtime, and in `Info.plist`) and its EdDSA public key at this repo.
4. Rewords the two UI strings that literally say "FORCE_LICENSED".

Every edit is anchored on a build setting, declaration or literal string rather than a line number, and a missing anchor is a hard failure: a red build beats a silently locked one.

Branches:

- **`tooling`** is the source of truth: the README source, the workflows, `tools/`.
- **`main`** is rebuilt as *upstream `master` + one commit of tooling*, so GitHub's comparison view reads "1 commit ahead". It is force-pushed; never edit it directly.
- **`unlocked`** is the pristine upstream release tag with the patch applied, regenerated on each new release. This is the exact source every release binary is built from.

A workflow checks for a new upstream release every hour, and a daily run backs it up. When there is one it regenerates `unlocked`, builds on a macOS runner, signs, publishes a release and updates the appcast. If a release can't be built, nothing is published and the previous release stays in place. A release whose tag doesn't carry that version's source (upstream sometimes publishes a binary-only release) is skipped until it does.

</details>

<details>
<summary><b>Signing</b></summary>

Builds are signed with a self-signed certificate and not notarized. The designated requirement is `identifier "com.nuebling.mac-mouse-fix" and certificate root = H"…"`, which doesn't change from build to build, so the Accessibility grant survives updates. Check yours:

```bash
codesign -d -r- "/Applications/Mac Mouse Fix.app"
```

</details>

<details>
<summary><b>Build it yourself</b></summary>

```bash
git clone --depth 1 --branch 3.1.0 https://github.com/noah-nuebling/mac-mouse-fix.git src
git clone --branch tooling https://github.com/oenderg/mac-mouse-fix-free.git ci
python3 ci/tools/unlock_pro.py src
bash ci/tools/build.sh src 3.1.0 "$PWD/dist"
```

You'll need Xcode. Without `SIGN_IDENTITY` set the app is ad-hoc signed, which works but loses its permission grants on every rebuild. The upstream project is built as its `App` scheme; no SwiftPM packages are fetched, everything is vendored.

</details>

<details>
<summary><b>Licence</b></summary>

Mac Mouse Fix is licensed under the [MMF License](https://github.com/noah-nuebling/mac-mouse-fix/blob/master/License), which is not a standard open-source licence. In short, it lets you publish a modified copy for free, and asks two things: that it's apparent the work is derived from Mac Mouse Fix, and — unless your source is a substantial, separate derivative work — that the monetization systems (licensing, trial, payment) be left in place and working.

This fork keeps all of that code but switches the trial off with upstream's own build flag, so it leans on the "substantial derivative work" reading for altering the monetization. Reasonable people could read it differently; the honest summary is that it is a **free, unofficial, derived build**, and upstream's purchase page is one click away in the app. If the author objects, this repo's `tooling` branch is the only copy, and this README is where to say so.

</details>

---

> ### Below is upstream's README, unmodified
>
> Install with the command above, not the download button or `brew`: those give the **official, locked** build. Pricing and the "free for 30 days" terms don't apply to this build.

---
