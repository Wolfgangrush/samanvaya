"""Entry point for the windowed build.

Mirrors ``entry.py``, which is the command-line entry point. PyInstaller needs a module to
start from and the console script declared in ``pyproject.toml`` is not one; this file
exists so the frozen application starts the window rather than the CLI.
"""

from samanvaya.gui import main

if __name__ == "__main__":
    raise SystemExit(main())
