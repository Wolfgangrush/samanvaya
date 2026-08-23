#!/usr/bin/env bash
# Build samanvaya as a double-clickable macOS application.
#
# WHY an .app and not a command-line binary in a zip: the user is an adviser, and the
# adviser is a lawyer. Packaging cannot fix a terminal — a .pkg or a .dmg containing a CLI
# still lands the user at a prompt with nothing to type. The window is the product surface
# for that user; the CLI remains for anyone who prefers it.
#
# WHY signed: this tool is run by professionals on client facts. Software that macOS
# reports as unverified is software a careful professional should not run, and telling
# them to disable a security control in order to use a compliance tool is a bad look with
# a worse principle behind it.
#
# NOT notarised by default. Notarisation is Apple's malware scan for software distributed
# OUTSIDE the App Store — it is not an App Store submission — but it needs App Store
# Connect credentials that have not been created. Without it macOS still warns on first
# open and the user must approve the app once in System Settings > Privacy & Security.
# If NOTARY_PROFILE is set the script submits, waits, and staples. See the notary note
# further down.
#
# INTERPRETER — this matters, do not "simplify" it back to Homebrew python.
# Build with uv's MANAGED standalone CPython, created as:
#     uv python install 3.13
#     uv venv --python "$(uv python find 3.13)" .venv
#     uv pip install --python .venv/bin/python -e '.[dev]' && uv pip install --python .venv/bin/python pyinstaller
# Two separate Homebrew defects made this necessary on 2026-08-20:
#   1. python@3.14's ensurepip is broken, so `python3 -m venv` exits non-zero with no pip.
#   2. python@3.13 3.13.15 and python@3.14 3.14.6 both ship a pyexpat linked against
#      /usr/lib/libexpat.1.dylib, which on macOS 26.1 lacks
#      _XML_SetAllocTrackerActivationThreshold. pyexpat therefore fails to load, plistlib
#      fails with it, platform.mac_ver() returns empty, and PyInstaller dies on
#      int('') deep inside its own compat module. `brew install expat` does NOT fix it:
#      the install name is baked into the extension.
# The standalone build bundles its own expat AND its own Tcl/Tk, so it sidesteps both.
#
# WHY A STAGE DIRECTORY OUTSIDE THE SYNCED TREE — this is load-bearing and is the
# reason the script is structured this way at all. ~/Desktop is under a cloud file
# provider (iCloud Drive and OneDrive both sync it). That provider continuously stamps
# 'com.apple.FinderInfo' and 'com.apple.fileprovider.fpfs#P' onto the .app bundle, and
# codesign then refuses with "resource fork, Finder information, or similar detritus not
# allowed". Stripping the attribute in place loses the race: the provider re-applies it
# within two seconds. The only reliable fix is to copy the bundle out of the synced
# tree with `ditto --norsrc --noextattr --noacl`, sign it THERE, and only copy the
# signed artefact back. The dist/ copy is for convenience only — it WILL be re-stamped
# by the provider and CANNOT be re-signed in place. Distribute the stage copy or the
# stage zip, not dist/samanvaya.app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"
APP_CERT="${APP_CERT:-Developer ID Application: Rushikesh Mahajan (743PSGX3AR)}"
NOTARY_PROFILE="${NOTARY_PROFILE:-}"

# STAGE lives outside the synced tree. "${TMPDIR:-/tmp}" is per-user and not under
# iCloud or OneDrive, so the provider cannot stamp attributes onto artefacts built
# there. See the STAGE note at the top of this script.
STAGE="${STAGE:-${TMPDIR:-/tmp}/samanvaya-build}"

[ -x "$PY" ] || { echo "error: no interpreter at $PY. See the INTERPRETER note at the top of this script." >&2; exit 2; }

# Tk is standard library, but Homebrew's python formula does NOT build _tkinter unless the
# matching python-tk formula is installed. Without it this build produces an app that dies
# on launch, so it is checked here rather than discovered by a user.
"$PY" -c 'import _tkinter' 2>/dev/null || {
  echo "error: this interpreter has no _tkinter." >&2
  echo "       brew install python-tk@3.13" >&2
  exit 2
}

"$PY" -c 'import PyInstaller' 2>/dev/null || uv pip install --python "$PY" -q pyinstaller

rm -rf build dist/samanvaya.app samanvaya-gui.spec

# --paths src           : uv's editable install leaves a .pth PyInstaller's static analysis
#                         never executes, so without this the build SUCCEEDS and the app
#                         dies with ModuleNotFoundError. Load-bearing; do not remove.
# --collect-submodules  : the regulatory packs are imported statically by registry.py, but
#                         collecting the subpackage explicitly means a future pack cannot go
#                         missing from the app while every test still passes.
# --collect-data fpdf   : fpdf2 ships a colour profile that is not a Python module.
# --windowed            : produces a .app bundle with no terminal window.
"$PY" -m PyInstaller \
  --windowed \
  --name samanvaya \
  --paths src \
  --collect-submodules samanvaya \
  --collect-data fpdf \
  --osx-bundle-identifier com.wolfgangrush.samanvaya \
  --clean --noconfirm \
  entry_gui.py

APP="dist/samanvaya.app"
[ -d "$APP" ] || { echo "error: no app bundle produced" >&2; exit 1; }

# STAMP THE VERSION INTO THE BUNDLE.
# PyInstaller's command line has no flag for CFBundleShortVersionString, so an unstamped
# bundle reports "0.0.0" in Finder's Get Info and in every crash report. On software a
# professional runs against client facts, "which build is this?" has to have an answer
# that does not depend on the person remembering when they downloaded it.
#   CFBundleShortVersionString = the human version   (0.2.0)
#   CFBundleVersion            = the artefact counter (2)
# Both are read from the package itself, so they cannot drift from what the PDF prints.
APP_VERSION="$("$PY" -c 'import sys; sys.path.insert(0, "src"); import samanvaya; print(samanvaya.__version__)')"
APP_BUILD="$("$PY" -c 'import sys; sys.path.insert(0, "src"); import samanvaya; print(samanvaya.__build__)')"
PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $APP_VERSION" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleShortVersionString string $APP_VERSION" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $APP_BUILD" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $APP_BUILD" "$PLIST"
echo "==> stamped $APP_VERSION (build $APP_BUILD) into Info.plist"

# Move the bundle OUT of the synced tree before signing. --norsrc skips resource forks,
# --noextattr drops the FinderInfo / fileprovider attributes the cloud daemon is
# continuously stamping on, --noacl avoids copying macOS ACLs that codesign would
# otherwise have to traverse. After this copy the bundle is clean and stays clean,
# because the file provider cannot reach it.
mkdir -p "$STAGE"
rm -rf "$STAGE/samanvaya.app" "$STAGE/samanvaya.zip" "$STAGE/samanvaya-notary.zip"
echo "==> staging to $STAGE (outside the synced tree)"
ditto --norsrc --noextattr --noacl "$APP" "$STAGE/samanvaya.app"

STAGE_APP="$STAGE/samanvaya.app"

echo "==> signing"
# Strip any attributes that survived the ditto, defensively. Codesign still refuses a
# bundle containing anything with "resource fork, Finder information, or similar
# detritus not allowed", and the cost of being thorough here is one syscall.
xattr -cr "$STAGE_APP"

SIGNED_OK=0
if security find-identity -v -p codesigning 2>/dev/null | grep -qF "$APP_CERT"; then
  # WHY --timestamp and not --timestamp=none: the secure timestamp is what binds the
  # signature to a point in time independent of the certificate's validity period. The
  # developer account may not be renewed; with a secure timestamp the signature still
  # verifies on machines that trust the issuing CA at the time the signature was made.
  # If the timestamp server cannot be reached, retry once without it and warn loudly:
  # a signature without a secure timestamp dies when the certificate does.
  if codesign --force --deep --timestamp --options runtime --sign "$APP_CERT" "$STAGE_APP" 2>/dev/null; then
    SIGNED_OK=1
    echo "    signed with Developer ID (secure timestamp included)"
  elif codesign --force --deep --timestamp=none --options runtime --sign "$APP_CERT" "$STAGE_APP" 2>/dev/null; then
    SIGNED_OK=1
    echo "    WARNING: timestamp server unreachable — signed WITHOUT a secure timestamp." >&2
    echo "    WARNING: this signature will become unverifiable when the certificate expires." >&2
    echo "    WARNING: re-run with network access to the timestamp server to obtain a long-lived signature." >&2
  else
    echo "    (Developer ID signing did not complete — run this from an interactive Terminal)" >&2
  fi
else
  echo "    WARNING: Developer ID certificate not found; ad-hoc signing." >&2
  echo "    WARNING: an ad-hoc signed app downloaded from GitHub WILL be refused by Gatekeeper." >&2
  if codesign --force --deep --options runtime --sign - "$STAGE_APP" 2>/dev/null; then
    SIGNED_OK=1
  fi
fi

# Non-fatal: signing cannot complete from a non-interactive shell (the keychain
# cannot prompt for the private key, and codesign degrades to ad-hoc while still
# returning 0). Failing the whole build on that would also skip the launch gate
# below, which is the check that actually matters. Sign from a real Terminal.
codesign --verify --strict --verbose=2 "$STAGE_APP" 2>&1 | sed 's/^/    /' || \
  echo "    (signature not verified — sign from an interactive Terminal)"

# Report the Gatekeeper verdict. On an UNNOTARISED Developer ID build this will read
# "rejected ... source=Unnotarized Developer ID". That is expected and is NOT a build
# failure — it is precisely why the notary step exists. Do not mistake it for broken.
echo "==> Gatekeeper assessment"
spctl --assess --type execute --verbose=4 "$STAGE_APP" 2>&1 | sed 's/^/    /' || \
  echo "    (rejected source=Unnotarized Developer ID is EXPECTED for an unsigned notarisation; see notary step)"

if [ -n "$NOTARY_PROFILE" ]; then
  echo "==> notarising"
  NOTARY_ZIP="$STAGE/samanvaya-notary.zip"
  # Use the stage copy, not dist/, for the same reason as signing: the provider would
  # stamp the artefact before notarytool could upload it. --keepParent preserves
  # samanvaya.app at the zip root so stapler can find the bundle.
  ditto -c -k --keepParent --norsrc --noextattr "$STAGE_APP" "$NOTARY_ZIP"
  xcrun notarytool submit "$NOTARY_ZIP" --keychain-profile "$NOTARY_PROFILE" --wait
  xcrun stapler staple "$STAGE_APP"
  echo "==> Gatekeeper re-assessment (post-notarisation)"
  spctl --assess --type execute --verbose=4 "$STAGE_APP" 2>&1 | sed 's/^/    /' || true
else
  cat <<'NOTE'
    NOT notarised (NOTARY_PROFILE unset). First launch on another Mac will warn; the user
    approves once in System Settings > Privacy & Security > Open Anyway. To remove that:
      xcrun notarytool store-credentials samanvaya-notary \
        --key /path/AuthKey_XXXX.p8 --key-id XXXX --issuer <issuer-uuid>
      NOTARY_PROFILE=samanvaya-notary ./build-app.sh
NOTE
fi

echo "==> distributable zip"
# Build the upload archive FROM the stage copy so the zip itself carries no provider
# attributes. --keepParent makes the zip root contain samanvaya.app, matching what
# users expect when they double-click the archive and get a folder containing an app.
DIST_ZIP="$STAGE/samanvaya.zip"
ditto -c -k --keepParent --norsrc --noextattr "$STAGE_APP" "$DIST_ZIP"
echo "    $DIST_ZIP"

# ---------------------------------------------------------------------------
# LAUNCH GATE — the build is not finished until the app actually starts.
#
# On 2026-08-20 this script reported a successful build of an application that
# died instantly with `AttributeError: module 'tkinter.ttk' has no attribute
# 'Menu'`. Every one of the 589 tests passed, because the tests cover the
# module's data and pure functions and deliberately never construct a widget.
# "PyInstaller exited 0" is a statement about PyInstaller, not about the app.
#
# So: start it, give it a few seconds, and require that it is STILL RUNNING.
# A GUI process that exits on its own within the window has crashed.
#
# Run this against the STAGE copy, not the dist copy, for the same reason as
# signing: we are testing the artefact that will actually be distributed.
# ---------------------------------------------------------------------------
echo "==> launch check"
"$STAGE_APP/Contents/MacOS/samanvaya" >/tmp/samanvaya-launch-check.log 2>&1 &
LAUNCH_PID=$!
sleep 6
if kill -0 "$LAUNCH_PID" 2>/dev/null; then
  kill "$LAUNCH_PID" 2>/dev/null || true
  wait "$LAUNCH_PID" 2>/dev/null || true
  echo "    app started and stayed running"
else
  echo "    FAILED — the app exited on its own. It is broken. Output:" >&2
  sed 's/^/    /' /tmp/samanvaya-launch-check.log >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# SELF-TEST GATE — the launch gate proves the app OPENS. This proves it WORKS.
#
# Every test in this repository runs against the source tree. What a user opens is
# this bundle, and the gap between the two has bitten twice. On 2026-08-20 the app
# died on launch with `AttributeError: module 'tkinter.ttk' has no attribute 'Menu'`
# while 589 tests passed, because none of them built a widget. The launch gate above
# was the answer to that, and it starts the binary, waits, and clicks nothing.
#
# The intake form is nine pages of widgets reached through a menu item. If form_view
# failed to bundle — a real possibility, since PyInstaller computes the import graph
# by static analysis — the launch gate would pass green and the crash would arrive
# the first time an adviser chose File > New Intake Form, in front of a client.
#
# So the bundle is asked to build every surface it has and report. A broken surface
# FAILS THE BUILD. It is not a substitute for a person using the product; it answers
# one question only: does every surface in this binary construct and run.
# ---------------------------------------------------------------------------
echo "==> self-test (every surface, inside the signed bundle)"
SELFTEST_REPORT="$STAGE/selftest-report.json"
SELFTEST_WORK="$STAGE/selftest-work"
rm -rf "$SELFTEST_WORK" "$SELFTEST_REPORT"
mkdir -p "$SELFTEST_WORK"

# TMPDIR is redirected into the stage so the self-test's scratch PDFs cannot land in
# the user's Desktop or a synced folder.
if ! TMPDIR="$SELFTEST_WORK" SAMANVAYA_SELFTEST="$SELFTEST_REPORT" \
     "$STAGE_APP/Contents/MacOS/samanvaya" >/tmp/samanvaya-selftest.log 2>&1; then
  echo "    FAILED — the self-test exited non-zero. Output:" >&2
  sed 's/^/    /' /tmp/samanvaya-selftest.log >&2
  [ -f "$SELFTEST_REPORT" ] && sed 's/^/    /' "$SELFTEST_REPORT" >&2
  exit 1
fi

[ -f "$SELFTEST_REPORT" ] || {
  echo "    FAILED — the self-test wrote no report. It did not run." >&2
  sed 's/^/    /' /tmp/samanvaya-selftest.log >&2
  exit 1
}

"$PY" - "$SELFTEST_REPORT" <<'SELFTEST_PY' || exit 1
import json
import sys

report = json.loads(open(sys.argv[1]).read())
surfaces = report.get("surfaces", {})
for name in sorted(surfaces):
    entry = surfaces[name]
    mark = "ok  " if entry.get("ok") else "FAIL"
    print(f"    {mark} {name}" + ("" if entry.get("ok") else f"  -- {entry.get('error')}"))
print(f"    build {report.get('version')} ({report.get('build')})")
if not report.get("ok"):
    print("    FAILED — a surface in the shipped bundle is broken.", file=sys.stderr)
    raise SystemExit(1)
SELFTEST_PY
echo "    every surface built and ran inside the bundle"

# Convenience copy back into ./dist. This WILL be re-stamped by the cloud file
# provider (iCloud Drive, OneDrive) and cannot be re-signed in place. It exists
# for local convenience only. Distribute the stage copy or the stage zip.
mkdir -p dist
rm -rf dist/samanvaya.app
ditto --norsrc --noextattr --noacl "$STAGE_APP" dist/samanvaya.app
echo
cat <<INFO
    built (signed, in stage):     $STAGE_APP
    built (distributable zip):    $DIST_ZIP
    built (convenience copy):     $ROOT/dist/samanvaya.app

    Distribute the STAGE copy or the STAGE zip. The dist/ copy is re-stamped by
    the cloud file provider and cannot be re-signed in place — it is for local
    use only.
INFO
du -sh "$STAGE_APP" "$DIST_ZIP" 2>/dev/null | awk '{print "       "$1"  "$2}'
