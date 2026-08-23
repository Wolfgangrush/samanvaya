#!/usr/bin/env bash
# Install the signed bundle into /Applications, and prove it works THERE.
#
# WHY THIS EXISTS AS A SCRIPT AND NOT A DRAG-AND-DROP
# There was no installed copy of this application on the maintainer's Mac for the first
# three weeks of its life. It was being opened out of `dist/`, which is a build output
# directory inside a cloud-synced folder — and that is exactly why copies named
# "samanvaya 2.app" through "samanvaya 6.app" kept appearing beside it, three of them
# still reporting version 0.0.0. A build directory is not an install location, and
# "which one did I open?" is not a question a professional tool should raise.
#
# WHY THE STAGE COPY AND NEVER dist/
# ~/Desktop is under a cloud file provider. It continuously stamps extended attributes
# onto anything inside it, which breaks code signatures. `build-app.sh` therefore signs
# in a stage directory outside the synced tree; the dist/ copy is a convenience that
# WILL be re-stamped and CANNOT be re-signed in place. Installing from dist/ would put a
# bundle with a broken signature into /Applications.
#
# WHY IT SELF-TESTS AFTER INSTALLING
# Verifying the artefact in the stage proves the stage copy works. The thing the user
# double-clicks is the installed copy, and copying is a step that can fail. The gate is
# run again against what actually landed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"
STAGE="${STAGE:-${TMPDIR:-/tmp}/samanvaya-build}"
STAGE_APP="$STAGE/samanvaya.app"
TARGET="${TARGET:-/Applications/samanvaya.app}"
BUNDLE_ID="com.wolfgangrush.samanvaya"

[ -d "$STAGE_APP" ] || {
  echo "error: no signed bundle at $STAGE_APP" >&2
  echo "       run ./build-app.sh first — do NOT install from dist/, its signature is" >&2
  echo "       broken by the cloud file provider." >&2
  exit 2
}

# ---- remove any previous install, but only if it is OURS -------------------------
# Checking the bundle identifier before deleting anything under /Applications is the
# difference between an upgrade and an accident.
if [ -e "$TARGET" ]; then
  EXISTING_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \
    "$TARGET/Contents/Info.plist" 2>/dev/null || echo "")"
  if [ "$EXISTING_ID" != "$BUNDLE_ID" ]; then
    echo "error: $TARGET exists and is not this application" >&2
    echo "       found bundle id: ${EXISTING_ID:-<none>}; expected: $BUNDLE_ID" >&2
    echo "       refusing to delete something that is not ours." >&2
    exit 2
  fi
  OLD_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
    "$TARGET/Contents/Info.plist" 2>/dev/null || echo "?")"
  OLD_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' \
    "$TARGET/Contents/Info.plist" 2>/dev/null || echo "?")"
  echo "==> removing installed $OLD_VERSION (build $OLD_BUILD)"
  # Quit it first: replacing a running bundle leaves the running copy on deleted inodes
  # and the next launch is a coin toss between old and new code.
  osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
  pkill -f "$TARGET/Contents/MacOS/samanvaya" 2>/dev/null || true
  rm -rf "$TARGET"
fi

echo "==> installing to $TARGET"
ditto --norsrc --noextattr --noacl "$STAGE_APP" "$TARGET"

# RE-REGISTER WITH LAUNCHSERVICES. This is not optional and it is not cosmetic.
#
# Removing a bundle and writing a new one at the same path leaves LaunchServices holding
# the registration of the bundle that no longer exists. `open`, Launchpad, Spotlight and
# a double-click in Finder all go through LaunchServices, so they launch a ghost that
# dies instantly and silently — while running the binary directly still works perfectly,
# because a direct exec bypasses LaunchServices altogether.
#
# That is what makes it dangerous: every script-shaped check passes and the only broken
# path is the one an actual person uses. Observed on this machine, 2026-08-22, on the
# first install of build 4.
echo "==> registering with LaunchServices"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
if [ -x "$LSREGISTER" ]; then
  "$LSREGISTER" -f "$TARGET" || echo "    WARNING: lsregister failed; a double-click may not work" >&2
else
  echo "    WARNING: lsregister not found at the expected path" >&2
fi

NEW_VERSION="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' \
  "$TARGET/Contents/Info.plist")"
NEW_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' \
  "$TARGET/Contents/Info.plist")"
echo "    installed $NEW_VERSION (build $NEW_BUILD)"

echo "==> signature, as installed"
codesign --verify --strict --verbose=2 "$TARGET" 2>&1 | sed 's/^/    /' || {
  echo "    FAILED — the installed copy does not verify. Do not run it." >&2
  exit 1
}

# Reported, never fatal. An unnotarised Developer ID build is rejected here by design;
# see the notary note in build-app.sh.
echo "==> Gatekeeper, as installed"
spctl --assess --type execute --verbose=4 "$TARGET" 2>&1 | sed 's/^/    /' || true

# ---- prove the INSTALLED copy works ------------------------------------------------
echo "==> self-test, against the installed copy"
REPORT="${TMPDIR:-/tmp}/samanvaya-install-selftest.json"
WORK="${TMPDIR:-/tmp}/samanvaya-install-selftest-work"
rm -rf "$WORK" "$REPORT"; mkdir -p "$WORK"

if ! TMPDIR="$WORK" SAMANVAYA_SELFTEST="$REPORT" \
     "$TARGET/Contents/MacOS/samanvaya" >/tmp/samanvaya-install-selftest.log 2>&1; then
  echo "    FAILED — the installed application is broken. Output:" >&2
  sed 's/^/    /' /tmp/samanvaya-install-selftest.log >&2
  exit 1
fi

"$PY" - "$REPORT" <<'REPORT_PY' || exit 1
import json
import sys

report = json.loads(open(sys.argv[1]).read())
for name in sorted(report.get("surfaces", {})):
    entry = report["surfaces"][name]
    mark = "ok  " if entry.get("ok") else "FAIL"
    print(f"    {mark} {name}" + ("" if entry.get("ok") else f"  -- {entry.get('error')}"))
if not report.get("ok"):
    print("    FAILED — a surface is broken in the installed copy.", file=sys.stderr)
    raise SystemExit(1)
REPORT_PY

# ---- prove it launches THE WAY A PERSON LAUNCHES IT --------------------------------
# The self-test above execs the binary directly. A user double-clicks, which goes through
# LaunchServices — a different code path, and the one that was broken. Testing only the
# path a script takes is how an installer reports success on an app nobody can open.
echo "==> double-click launch (via LaunchServices, as a person would)"
osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
sleep 1
open "$TARGET"
sleep 6
if pgrep -f "$TARGET/Contents/MacOS/samanvaya" >/dev/null 2>&1; then
  echo "    opened and stayed running"
else
  echo "    FAILED — the application does not start when opened normally," >&2
  echo "    even though the binary runs when executed directly. This is the" >&2
  echo "    LaunchServices registration failure described above." >&2
  exit 1
fi

echo
echo "    installed and verified: $TARGET  ($NEW_VERSION build $NEW_BUILD)"
echo "    open it from Launchpad, Spotlight, or:  open '$TARGET'"
