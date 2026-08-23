#!/usr/bin/env bash
# Build samanvaya as a single-file executable.
#
# WHY a single file: the people who use this are advisers, not Python users. "Install
# Python 3.13, create a virtualenv, pip install" is not a distribution channel. One
# downloadable file that runs is.
#
# WHY fpdf2 and not a headless browser: a single-file binary cannot depend on Chrome
# being present on the target machine, and a bundled browser is a renderer with its own
# CVE history riding inside a legal tool. fpdf2 is pure Python and bundles cleanly.
#
# Run from the project root. Produces dist/samanvaya.
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
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="${VENV:-.venv}"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "error: no interpreter at $PY" >&2
  echo "       create one with:  uv python install 3.13 && uv venv --python \"$(uv python find 3.13)\" .venv" >&2
  echo "       note: python3 -m venv fails on Homebrew Python 3.14 (ensurepip is broken)" >&2
  exit 2
fi

"$PY" -c 'import PyInstaller' 2>/dev/null || {
  echo "installing PyInstaller into $VENV"
  uv pip install --python "$PY" -q pyinstaller
}

rm -rf build dist samanvaya.spec

# --collect-data fpdf : fpdf2 ships a colour profile under fpdf/data that is not a
#                       Python module, so PyInstaller's import graph does not find it.
# --console           : this is a CLI; a windowed build would give the user no output.
# --paths src : the venv installs this project editable, and uv's editable install
#               places a .pth that PyInstaller's static analysis does not execute, so
#               without this the build SUCCEEDS and produces a binary that dies on
#               `ModuleNotFoundError: No module named 'samanvaya'`. Pointing the
#               analysis at the real source tree is the fix; do not remove it.
# --collect-submodules samanvaya : the six regulatory packs are imported statically by
#               registry.py, but collecting the subpackage explicitly means a future
#               pack cannot go missing from the binary while the tests still pass.
"$PY" -m PyInstaller \
  --onefile \
  --console \
  --name samanvaya \
  --paths src \
  --collect-submodules samanvaya \
  --collect-data fpdf \
  --clean \
  --noconfirm \
  entry.py

echo
echo "built: $ROOT/dist/samanvaya"
ls -lh dist/samanvaya
